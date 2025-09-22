"""
Intent parser module that converts natural speech to structured browser commands.
Designed to be token-efficient and resilient to rate limits.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

# ---- Global rate guard so we don't blast TPM with parallel calls ----
_OPENAI_SEMAPHORE = asyncio.Semaphore(1)

# ---- Defaults (tune as needed) ----
INTENT_MODEL = getattr(settings, "openai_intent_model", "gpt-4o-mini")  # small & fast for intent
MAX_CTX_CHARS = 400
INTENT_MAX_TOKENS = 64
MULTISTEP_MAX_TOKENS = 196  # short JSON array only

# Debounce & quality gates
MIN_TOKENS = 3
MIN_CONFIDENCE = 0.60


def _summarize_context(ctx: Dict[str, Any], limit: int = MAX_CTX_CHARS) -> str:
    """Compact JSON dump of context with hard char limit (avoid token blowups)."""
    if not ctx:
        return ""
    try:
        s = json.dumps(ctx, separators=(",", ":"), ensure_ascii=False)
        return (s[:limit] + "…") if len(s) > limit else s
    except Exception:
        return ""


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Safely extract a JSON object from a model response."""
    if not text:
        return {"intent": "NOOP", "confidence": 0.0, "parameters": {}}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j != -1 and j > i:
        try:
            data = json.loads(text[i:j+1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"intent": "NOOP", "confidence": 0.0, "parameters": {}}


def _extract_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    """Extract a JSON array from text; return None if not found/invalid."""
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    i, j = text.find("["), text.rfind("]")
    if i != -1 and j != -1 and j > i:
        try:
            data = json.loads(text[i:j+1])
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return None


def _normalize_intent_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure required fields + types; coerce intent to UPPER; clamp confidence."""
    intent = str(obj.get("intent", "NOOP") or "NOOP").upper()
    conf = obj.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    params = obj.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
    norm = {"intent": intent, "confidence": conf, "parameters": params}
    if "context" in obj:   # passthrough optional fields if present
        norm["context"] = obj["context"]
    if "follow_up" in obj:
        norm["follow_up"] = obj["follow_up"]
    return norm


async def _call_openai_with_backoff(fn, *args, **kwargs):
    """Retry with exponential backoff on rate/temporary errors."""
    delay = 0.45
    for attempt in range(6):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "temporar" in msg or "overload" in msg or "timeout" in msg:
                wait = delay + (0.2 * attempt)
                logger.warning(f"OpenAI call throttled (attempt {attempt+1}). Sleeping {wait:.2f}s")
                await asyncio.sleep(wait)
                delay *= 1.8
                continue
            raise


class IntentParser:
    """
    Converts natural language to structured browser commands using OpenAI.

    JSON contract:
    {
      "intent": "COMMAND_TYPE",
      "confidence": 0.95,
      "parameters": { ... },
      "context": "...",          # optional
      "follow_up": ["..."]       # optional
    }

    COMMAND_TYPE ∈ {
      NAVIGATE, SEARCH, CLICK, TYPE, EXTRACT, SCROLL, WAIT, SCREENSHOT, FILTER, FILL_FORM, DOWNLOAD, UPLOAD
    }
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        # Terse prompt to minimize tokens; examples stay compact.
        return (
            "You convert short voice commands into COMPACT JSON ONLY with keys: "
            "`intent` (one of NAVIGATE, SEARCH, CLICK, TYPE, EXTRACT, SCROLL, WAIT, SCREENSHOT, FILTER, FILL_FORM, DOWNLOAD, UPLOAD), "
            "`confidence` (0..1), and `parameters` (object). "
            "For CLICK/TYPE, if the user references an on-page element with words (e.g., 'Women', 'Pick Up Today'), "
            "return that phrase in `selector` (do NOT invent CSS). "
            "If the user references an area like 'on the left', include `scope` with a short phrase (e.g., 'left sidebar', 'header'). "
            "Never include prose or explanations.\n\n"
            "Examples:\n"
            "- Go to Google -> {\"intent\":\"NAVIGATE\",\"confidence\":0.98,\"parameters\":{\"target\":\"https://google.com\"}}\n"
            "- Search for Python tutorials -> {\"intent\":\"SEARCH\",\"confidence\":0.97,\"parameters\":{\"text\":\"Python tutorials\"}}\n"
            "- Click the Women menu -> {\"intent\":\"CLICK\",\"confidence\":0.93,\"parameters\":{\"selector\":\"Women\",\"scope\":\"header\"}}\n"
            "- Toggle Pick Up Today -> {\"intent\":\"CLICK\",\"confidence\":0.90,\"parameters\":{\"selector\":\"Pick Up Today\",\"scope\":\"left sidebar\"}}\n"
            "- Screenshot -> {\"intent\":\"SCREENSHOT\",\"confidence\":0.99,\"parameters\":{}}\n"
            "If unclear, return a low confidence with intent \"NOOP\"."
        )

    def _gate(self, transcript: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Apply local gates to avoid junk actions from partial utterances."""
        tokens = len((transcript or "").strip().split())
        if tokens < MIN_TOKENS:
            return {"intent": "NOOP", "confidence": 0.0, "parameters": {}}
        if (parsed.get("intent") or "").upper() == "NOOP":
            return parsed
        if float(parsed.get("confidence", 0.0) or 0.0) < MIN_CONFIDENCE:
            # downgrade to NOOP to avoid spurious clicks
            return {"intent": "NOOP", "confidence": parsed.get("confidence", 0.0), "parameters": {}}
        return parsed

    async def parse_intent(self, transcript: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse a single voice transcript into a structured intent."""
        try:
            if len(transcript.strip().split()) < MIN_TOKENS:
                return {"intent": "NOOP", "confidence": 0.0, "parameters": {}}

            ctx = _summarize_context(context or {}, MAX_CTX_CHARS)
            user = f"Voice: {transcript.strip()}"
            if ctx:
                user += f"\nCTX:{ctx}"

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user},
            ]

            async with _OPENAI_SEMAPHORE:
                resp = await _call_openai_with_backoff(
                    self.client.chat.completions.create,
                    model=INTENT_MODEL,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=INTENT_MAX_TOKENS,
                    response_format={"type": "json_object"},  # force JSON
                )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            raw = _extract_json_object(content)
            intent = _normalize_intent_shape(raw)
            intent = self._gate(transcript, intent)
            logger.info(f"Parsed intent: {intent}")
            return intent

        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return {
                "intent": "ERROR",
                "confidence": 0.0,
                "parameters": {},
                "context": f"Failed to parse intent: {str(e)}",
                "follow_up": [],
            }

    async def parse_multi_step_intent(
        self, transcript: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse a complex command into a short sequence of intents.
        Returns a JSON array of single-intent objects (same schema as parse_intent).
        """
        try:
            if len(transcript.strip().split()) < max(MIN_TOKENS, 3):
                return [await self.parse_intent(transcript, context)]

            ctx = _summarize_context(context or {}, MAX_CTX_CHARS)
            prompt = (
                "Break the voice command into a SHORT sequence of actionable intents. "
                "Output JSON ARRAY ONLY; each item must follow the same JSON shape as single intent. "
                "For CLICK/TYPE items, keep `selector` as a human phrase (not CSS). Include `scope` if the user mentioned a page area.\n"
                f"Voice: {transcript.strip()}"
            )
            if ctx:
                prompt += f"\nCTX:{ctx}"

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]

            async with _OPENAI_SEMAPHORE:
                resp = await _call_openai_with_backoff(
                    self.client.chat.completions.create,
                    model=INTENT_MODEL,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=MULTISTEP_MAX_TOKENS,
                )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            arr = _extract_json_array(content)

            if arr:
                out: List[Dict[str, Any]] = []
                for item in arr[:6]:  # cap to avoid runaway sequences
                    if isinstance(item, dict):
                        norm = _normalize_intent_shape(item)
                        norm = self._gate(transcript, norm)
                        out.append(norm)
                if out:
                    logger.info(f"Parsed multi-step intents: {len(out)} steps")
                    return out

            single = await self.parse_intent(transcript, context)
            return [single]

        except Exception as e:
            logger.error(f"Error parsing multi-step intent: {e}")
            return [
                {
                    "intent": "ERROR",
                    "confidence": 0.0,
                    "parameters": {},
                    "context": f"Failed to parse multi-step intent: {str(e)}",
                    "follow_up": [],
                }
            ]

    # ---- Optional helpers (unchanged API) ----
    def validate_intent(self, intent_data: Dict[str, Any]) -> bool:
        """Validate that the parsed intent has required fields."""
        required_fields = ["intent", "confidence", "parameters"]
        return all(field in intent_data for field in required_fields)

    def get_intent_summary(self, intent_data: Dict[str, Any]) -> str:
        """Human-readable one-liner for logs/UX."""
        intent = intent_data.get("intent", "UNKNOWN")
        confidence = float(intent_data.get("confidence", 0.0) or 0.0)
        parameters = intent_data.get("parameters", {}) or {}

        summary = f"Intent: {intent} (confidence: {confidence:.2f})"
        if parameters:
            key_params = []
            for key in ("target", "text", "selector", "data_type", "scope"):
                val = parameters.get(key)
                if val:
                    key_params.append(f"{key}: {val}")
            if key_params:
                summary += " - " + ", ".join(key_params)
        return summary
