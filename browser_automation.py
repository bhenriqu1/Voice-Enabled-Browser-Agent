import os
import json
import base64
import asyncio
import logging
from typing import Dict, List, Optional, Any

import aiohttp
from aiohttp import ClientTimeout
import websockets

from config import settings

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """Browser automation using Browserbase Sessions API + Stagehand (no Selenium)."""

    def __init__(self):
        # Config / state
        self.api_key: str = settings.browserbase_api_key
        self.project_id: str = settings.browserbase_project_id
        self.base_url: str = "https://api.browserbase.com/v1"

        # HTTP + session state
        self.http: Optional[aiohttp.ClientSession] = None
        self._timeout = ClientTimeout(total=(getattr(settings, "browser_timeout", 60) or 60) + 15)
        self._lock = asyncio.Lock()

        # Browserbase session details
        self.session_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    # ---------- Context management ----------
    async def __aenter__(self):
        await self._ensure_http()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.shutdown()

    async def shutdown(self):
        """End BB session, close WebSocket + HTTP client."""
        try:
            if self.ws:
                try:
                    await self.ws.close()
                finally:
                    self.ws = None
            await self.end_session()
        finally:
            if self.http and not self.http.closed:
                # If your aiohttp supports aclose(), you can use that instead.
                await self.http.close()
                self.http = None
            # Give aiohttp a tick to flush connectors
            await asyncio.sleep(0)

    # ---------- HTTP utilities ----------
    async def _ensure_http(self):
        if self.http and not self.http.closed:
            return
        # ✅ Browserbase Sessions API expects X-BB-API-Key
        self.http = aiohttp.ClientSession(
            headers={"X-BB-API-Key": self.api_key},
            timeout=self._timeout,
        )

    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        await self._ensure_http()
        return await self.http.request(method, url, **kwargs)

    # ---------- Session lifecycle ----------
    async def start_session(self, force_new: bool = False) -> str:
        async with self._lock:
            if self.session_id and not force_new:
                return self.session_id

            payload: Dict[str, Any] = {}
            if self.project_id:
                payload["projectId"] = self.project_id

            resp = await self._request("POST", f"{self.base_url}/sessions", json=payload)
            txt = await resp.text()
            if resp.status not in (200, 201):
                raise RuntimeError(f"Failed to create session: {resp.status} {txt}")

            data = json.loads(txt)
            self.session_id = data["id"]
            logger.info(f"Started browser session: {self.session_id}")

            # Connect Stagehand WebSocket (apiKey & sessionId in query)
            ws_url = f"wss://connect.browserbase.com?sessionId={self.session_id}&apiKey={self.api_key}"
            for attempt in range(3):
                try:
                    self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=20)
                    logger.info("Connected to Stagehand WS")
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))

            return self.session_id

    async def end_session(self) -> None:
        if not self.session_id:
            return
        sid = self.session_id
        try:
            resp = await self._request("DELETE", f"{self.base_url}/sessions/{sid}")
            # Read body to release the connection cleanly (prevents “Unclosed connector” warnings)
            try:
                await resp.text()
            except Exception:
                pass
            logger.info(f"Ended browser session: {sid} (status {resp.status})")
        except Exception as e:
            logger.warning(f"Error ending session {sid}: {e}")
        finally:
            self.session_id = None

    # ---------- Low-level Stagehand send/recv ----------
    async def _send(self, action: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
        if not self.session_id:
            await self.start_session()
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        await self.ws.send(json.dumps(action))
        msg = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        try:
            return json.loads(msg)
        except Exception:
            return {"raw": msg}

    # ---------- Intent translator (keeps your old shape working) ----------
    def _intent_to_stagehand(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts your old shape:
            {"intent":"NAVIGATE","parameters":{"target":"https://..."}}
        into Stagehand actions, e.g.:
            {"type":"navigate","url":"https://..."}
        """
        if "type" in intent:
            return intent  # already a Stagehand action

        t = (intent.get("intent") or "").upper()
        p = intent.get("parameters") or {}

        if t == "NAVIGATE":
            return {"type": "navigate", "url": p.get("target", "about:blank")}
        if t == "SEARCH":
            # Type into a selector (fallback to google box)
            return {"type": "type", "selector": p.get("selector") or "input[name='q']", "text": p.get("text", "")}
        if t == "CLICK":
            return {"type": "click", "selector": p.get("selector", "")}
        if t == "TYPE":
            return {"type": "type", "selector": p.get("selector"), "text": p.get("text", "")}
        if t == "SCROLL":
            direction = (p.get("direction") or "down").lower()
            amount = 800 if direction == "down" else -800
            return {"type": "scrollBy", "x": 0, "y": amount}
        if t == "PRESS":
            return {"type": "press", "key": p.get("key", "Enter")}
        if t == "EXTRACT":
            return {"type": "extract", "selector": p.get("selector") or "body"}
        if t == "WAIT":
            return {"type": "sleep", "ms": int(p.get("timeout", 1)) * 1000}
        # Default: pass-through raw Stagehand action if provided under parameters.action
        return p.get("action") or {"type": "noop"}

    # ---------- Stagehand command execution ----------
    async def execute_command(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        action = self._intent_to_stagehand(intent)
        try:
            data = await self._send(action)
            return {"success": True, "action": action, "response": data}
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return {"success": False, "error": str(e), "action": action}

    async def execute_workflow(self, intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i, intent in enumerate(intents, start=1):
            logger.info(f"Executing step {i}/{len(intents)}: {intent.get('intent') or intent.get('type', 'UNKNOWN')}")
            result = await self.execute_command(intent)
            results.append({"step": i, "intent": intent, "result": result, "success": bool(result.get("success"))})
            await asyncio.sleep(0.2)
        logger.info(f"Workflow completed: {len(results)} steps executed")
        return results

    # ---------- Helpers expected by voice_browser_agent ----------
    async def get_page_content(self) -> Optional[Dict[str, Any]]:
        """
        Returns basic page info (url, title, text, html) using Stagehand.
        Uses a generic 'eval' action to run JS in the page; if your Stagehand
        dialect doesn't support 'eval', replace with the provider's equivalent.
        """
        try:
            # title
            t = await self._send({"type": "eval", "expression": "document.title"})
            title = t.get("result") or t.get("data") or ""

            # url
            u = await self._send({"type": "eval", "expression": "location.href"})
            url = u.get("result") or u.get("data") or ""

            # text
            x = await self._send({"type": "eval", "expression": "document.body && document.body.innerText || ''"})
            text = x.get("result") or x.get("data") or ""

            # html
            h = await self._send({"type": "eval", "expression": "document.documentElement.outerHTML"})
            html = h.get("result") or h.get("data") or ""

            return {"url": url, "title": title, "text": text, "html": html}
        except Exception as e:
            logger.error(f"get_page_content failed: {e}")
            return None

    async def take_screenshot(self) -> Optional[bytes]:
        """
        Grabs a PNG screenshot via Stagehand. Many providers return base64.
        Adjust keys as needed for your Stagehand response schema.
        """
        try:
            r = await self._send({"type": "screenshot", "format": "png", "return": "base64"})
            # Common keys to check:
            b64 = (
                r.get("response", {}).get("data")
                or r.get("data")
                or r.get("screenshot")
                or r.get("png")
            )
            if not b64:
                return None
            return base64.b64decode(b64)
        except Exception as e:
            logger.error(f"take_screenshot failed: {e}")
            return None

    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        """
        Waits for an element using Stagehand. Replace 'waitFor' with your provider's exact op if different.
        """
        try:
            r = await self._send({"type": "waitFor", "selector": selector, "timeoutMs": timeout * 1000})
            return bool(r)
        except Exception:
            return False

    async def extract_data(self, data_type: str = "text") -> Optional[Dict[str, Any]]:
        """
        Extracts basic data using Stagehand. Tuned to match your old helpers.
        """
        try:
            if data_type == "links":
                # Get hrefs via JS
                r = await self._send({"type": "eval", "expression": """
                    Array.from(document.querySelectorAll('a'))
                      .map(a => ({url: a.href || '', text: (a.textContent || '').trim()}))
                """})
                links = r.get("result") or r.get("data") or []
                return {"links": links, "count": len(links)}
            elif data_type == "images":
                r = await self._send({"type": "eval", "expression": """
                    Array.from(document.querySelectorAll('img'))
                      .map(img => ({src: img.src || '', alt: img.alt || ''}))
                """})
                images = r.get("result") or r.get("data") or []
                return {"images": images, "count": len(images)}
            elif data_type == "forms":
                r = await self._send({"type": "eval", "expression": """
                    Array.from(document.querySelectorAll('form')).map(form => ({
                        action: form.getAttribute('action') || '',
                        method: (form.getAttribute('method') || 'GET').toUpperCase(),
                        fields: Array.from(form.querySelectorAll('input, select, textarea')).map(f => ({
                            type: (f.getAttribute('type') || f.tagName || '').toLowerCase(),
                            name: f.getAttribute('name') || '',
                            id: f.id || '',
                            placeholder: f.getAttribute('placeholder') || ''
                        }))
                    }))
                """})
                forms = r.get("result") or r.get("data") or []
                return {"forms": forms, "count": len(forms)}
            else:
                r = await self._send({"type": "eval", "expression": "document.body && document.body.innerText || ''"})
                t = await self._send({"type": "eval", "expression": "document.title"})
                u = await self._send({"type": "eval", "expression": "location.href"})
                return {"text": r.get("result") or r.get("data") or "",
                        "title": t.get("result") or t.get("data") or "",
                        "url": u.get("result") or u.get("data") or ""}
        except Exception as e:
            logger.error(f"extract_data({data_type}) failed: {e}")
            return None


# ---------- Convenience runner ----------
async def run_workflow(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    async with BrowserAutomation() as b:
        await b.start_session()
        return await b.execute_workflow(intents)
