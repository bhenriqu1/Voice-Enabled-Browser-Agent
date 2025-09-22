import os
import re
import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple

import aiohttp
from aiohttp import ClientTimeout
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, expect

from config import settings

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """
    Browser automation using Browserbase Sessions API + Playwright over CDP.

    What you get:
    - A Browserbase session (POST /v1/sessions) and a live, watchable Debugger URL.
    - A Playwright connection to that session via connectUrl (CDP).
    - Helpers: execute_command, get_page_content, take_screenshot, wait_for_element, extract_data.
    - After NAVIGATE we take a screenshot to ./screenshots/<ts>.png.

    To watch the browser live, open the printed "Debugger URL (watch in your browser)" line.
    """

    def __init__(self):
        # API config
        self.api_key: str = settings.browserbase_api_key
        self.project_id: Optional[str] = getattr(settings, "browserbase_project_id", None)
        self.base_url: str = "https://api.browserbase.com/v1"

        # HTTP client
        self.http: Optional[aiohttp.ClientSession] = None
        self._timeout = ClientTimeout(total=(getattr(settings, "browser_timeout", 60) or 60) + 15)

        # Session state
        self.session_id: Optional[str] = None
        self.connect_url: Optional[str] = None
        self.debugger_url: Optional[str] = None

        # Playwright state
        self._pw = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Concurrency guards
        self._start_lock = asyncio.Lock()
        self._action_lock = asyncio.Lock()

        # Local persistence to avoid concurrent-limit annoyances
        self._state_file = getattr(settings, "browser_state_path", ".bb_session.json")

    # ---------- Context management ----------
    async def __aenter__(self):
        await self._ensure_http()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.shutdown()

    async def shutdown(self):
        """Close Playwright, end Browserbase session, and close HTTP session."""
        try:
            if self.page:
                try: await self.page.close()
                except Exception: pass
                self.page = None

            if self.context:
                try: await self.context.close()
                except Exception: pass
                self.context = None

            if self.browser:
                try: await self.browser.close()
                except Exception: pass
                self.browser = None

            if self._pw:
                try: await self._pw.stop()
                except Exception: pass
                self._pw = None

            await self.end_session()
        finally:
            if self.http and not self.http.closed:
                await self.http.close()
                self.http = None
            await asyncio.sleep(0)

    # ---------- HTTP utilities ----------
    async def _ensure_http(self):
        if self.http and not self.http.closed:
            return
        self.http = aiohttp.ClientSession(
            headers={"X-BB-API-Key": self.api_key},
            timeout=self._timeout,
        )

    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        await self._ensure_http()
        return await self.http.request(method, url, **kwargs)

    # ---------- State persistence ----------
    def _save_state(self, data: dict) -> None:
        try:
            with open(self._state_file, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load_state(self) -> Optional[dict]:
        if not os.path.exists(self._state_file):
            return None
        try:
            with open(self._state_file) as f:
                return json.load(f)
        except Exception:
            return None

    def _clear_state(self) -> None:
        try:
            if os.path.exists(self._state_file):
                os.remove(self._state_file)
        except Exception:
            pass

    # ---------- Session lifecycle ----------
    async def start_session(self, force_new: bool = False) -> str:
        async with self._start_lock:
            if self.session_id and not force_new:
                return self.session_id

            # Best-effort: clean any prior session
            prev = self._load_state() or {}
            prev_id = prev.get("id")
            if prev_id:
                try:
                    await self._request("DELETE", f"{self.base_url}/sessions/{prev_id}")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                finally:
                    self._clear_state()

            # Create Browserbase session
            payload: Dict[str, Any] = {}
            if self.project_id:
                payload["projectId"] = self.project_id

            resp = await self._request("POST", f"{self.base_url}/sessions", json=payload)
            txt = await resp.text()
            if resp.status == 401:
                raise RuntimeError(f"401 Unauthorized creating session: {txt}")
            if resp.status == 402:
                raise RuntimeError(f"402 Payment Required (minutes exhausted): {txt}")
            if resp.status not in (200, 201):
                raise RuntimeError(f"Failed to create session: {resp.status} {txt}")

            data = json.loads(txt)
            self.session_id = data["id"]
            self.connect_url = data.get("connectUrl")
            logger.info(f"Started browser session: {self.session_id}")

            # Fetch Debugger URL
            try:
                dbg = await self._request("GET", f"{self.base_url}/sessions/{self.session_id}/debug")
                dbg_json = await dbg.json()
                self.debugger_url = dbg_json.get("debuggerUrl") or dbg_json.get("viewerUrl")
                if self.debugger_url:
                    logger.info(f"Debugger URL (watch in your browser): {self.debugger_url}")
                    print(f"\n🔎 Debugger URL (open in your browser to watch): {self.debugger_url}\n")
            except Exception as e:
                logger.warning(f"Could not fetch debugger URL: {e}")

            # Connect Playwright over CDP
            if not self.connect_url:
                raise RuntimeError("Session did not return connectUrl; cannot attach Playwright.")
            self._pw = await async_playwright().start()
            self.browser = await self._pw.chromium.connect_over_cdp(self.connect_url)

            contexts = self.browser.contexts
            self.context = contexts[0] if contexts else await self.browser.new_context()
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()

            # Persist meta
            self._save_state({
                "id": self.session_id,
                "connectUrl": self.connect_url,
                "debuggerUrl": self.debugger_url,
                "projectId": self.project_id,
                "createdAt": time.time(),
            })
            return self.session_id

    async def end_session(self) -> None:
        if not self.session_id:
            return
        sid = self.session_id
        try:
            resp = await self._request("DELETE", f"{self.base_url}/sessions/{sid}")
            try:
                await resp.text()
            except Exception:
                pass
            logger.info(f"Ended browser session: {sid} (status {resp.status})")
        except Exception as e:
            logger.warning(f"Error ending session {sid}: {e}")
        finally:
            self._clear_state()
            self.session_id = None

    # ---------- Helpers ----------
    async def current_url(self) -> str:
        return self.page.url if self.page else ""

    async def _autosshot(self) -> Optional[str]:
        if not self.page:
            return None
        try:
            os.makedirs("screenshots", exist_ok=True)
            path = os.path.join("screenshots", f"{int(time.time())}.png")
            await self.page.screenshot(path=path, full_page=True)
            logger.info(f"Saved screenshot → {path}")
            return path
        except Exception as e:
            logger.warning(f"Auto-screenshot failed: {e}")
            return None

    def _pick_search_selector(self, url: str, provided: Optional[str]) -> str:
        """Choose a reasonable search box selector based on site, or use provided."""
        if provided:
            return provided
        u = (url or "").lower()
        if "youtube.com" in u:
            return "input#search"
        if "google." in u:
            return "textarea[name='q'],input[name='q']"
        if "bing.com" in u:
            return "input[name='q']"
        if "amazon." in u:
            return "input#twotabsearchtextbox"
        # generic fallback
        return "input[type='search'],input[name='q'],input[aria-label='Search'],[role='searchbox']"

    # ---------- Natural-language → locator resolver ----------
    async def _click_by_phrase(
        self,
        phrase: str,
        scope_hint: Optional[str] = None,
        hover_first: bool = True,
        timeout_ms: int = 8000,
    ) -> Tuple[bool, str]:
        """
        Try multiple strategies to click an element referenced by human phrase (e.g. 'Women', 'Pick Up Today').
        Returns (ok, debug_message).
        """
        if not self.page:
            return False, "No page"

        phrase = (phrase or "").strip()
        if not phrase:
            return False, "Empty phrase"

        def _region(scope: Optional[str]):
            if not scope:
                return self.page
            s = scope.lower()
            # common regions
            if "left" in s and ("hand" in s or "side" in s or "sidebar" in s):
                return self.page.locator("aside, [role='complementary'], [data-region='left'], [aria-label*='filter']").first
            if "top" in s or "header" in s or "nav" in s:
                return self.page.locator("header, nav").first
            if "footer" in s or "bottom" in s:
                return self.page.locator("footer").first
            if "filter" in s or "refine" in s:
                return self.page.locator("[aria-label*='Filter'], [data-testid*='filter'], [id*='filter']").first
            return self.page

        region = _region(scope_hint)

        # Build candidate strategies in order of robustness: role→text→css
        strategies = []

        # 1) role-based by accessible name (exact and fuzzy)
        strategies += [
            ("role:link exact", region.get_by_role("link", name=phrase, exact=True)),
            ("role:button exact", region.get_by_role("button", name=phrase, exact=True)),
            ("role:link fuzzy", region.get_by_role("link", name=re.compile(re.escape(phrase), re.I))),
            ("role:button fuzzy", region.get_by_role("button", name=re.compile(re.escape(phrase), re.I))),
        ]

        # 2) visible text
        strategies += [
            ("text exact", region.get_by_text(phrase, exact=True)),
            ("text fuzzy", region.get_by_text(re.compile(re.escape(phrase), re.I))),
        ]

        # 3) CSS hints
        css_hints = [
            f"[aria-label*='{phrase}']",
            f"[data-testid*='{phrase}']",
            f"a:has-text('{phrase}')",
            f"button:has-text('{phrase}')",
            f"label:has-text('{phrase}')",
        ]
        for sel in css_hints:
            strategies.append((f"css:{sel}", region.locator(sel)))

        # Try each strategy with visibility + optional hover then click
        last_err = ""
        for name, loc in strategies:
            try:
                cnt = await loc.count()
                logger.info(f"[selector-resolver] strategy={name} matches={cnt} phrase='{phrase}'")
                if cnt == 0:
                    continue
                target = loc.first
                await target.wait_for(state="visible", timeout=timeout_ms)
                if hover_first:
                    try:
                        await target.hover(timeout=2000)
                    except Exception:
                        pass
                await target.click(timeout=timeout_ms)
                return True, f"clicked via {name}"
            except Exception as e:
                last_err = f"{name} failed: {e}"

        return False, last_err or "no match"

    async def _site_search(self, query: str) -> bool:
        """Find a search box on the current page and submit the query (Enter)."""
        if not self.page:
            return False
        url = (self.page.url or "").lower()
        boxes = [
            self.page.get_by_role("searchbox"),
            self.page.locator("input[type='search']"),
            self.page.locator("input[name='q']"),
            self.page.locator("input[placeholder*='Search' i]"),
            self.page.locator("[aria-label*='Search' i]"),
        ]
        for box in boxes:
            try:
                await box.first.wait_for(state="visible", timeout=4000)
                await box.first.click()
                await box.first.fill("")  # clear
                await box.first.type(query, delay=20)
                await self.page.keyboard.press("Enter")
                # basic waits
                if "google." in url:
                    await self.page.wait_for_selector("#search, #rso", timeout=15000)
                elif "youtube.com" in url:
                    await self.page.wait_for_selector("ytd-video-renderer,ytd-rich-item-renderer", timeout=15000)
                else:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                return True
            except Exception:
                continue
        return False

    # ---------- Public helpers ----------
    async def get_page_content(self) -> Optional[Dict[str, Any]]:
        if not self.page:
            return None
        try:
            title = await self.page.title()
            url = self.page.url
            text = await self.page.evaluate("document.body && document.body.innerText || ''")
            html = await self.page.content()
            return {"url": url, "title": title, "text": text, "html": html}
        except Exception as e:
            logger.error(f"get_page_content failed: {e}")
            return None

    async def take_screenshot(self) -> Optional[bytes]:
        if not self.page:
            return None
        try:
            os.makedirs("screenshots", exist_ok=True)
            path = os.path.join("screenshots", f"{int(time.time())}.png")
            png = await self.page.screenshot(path=path, full_page=True)
            logger.info(f"Saved screenshot → {path}")
            return png
        except Exception as e:
            logger.error(f"take_screenshot failed: {e}")
            return None

    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        if not self.page:
            return False
        try:
            await self.page.wait_for_selector(selector, timeout=timeout * 1000)
            return True
        except Exception:
            return False

    async def extract_data(self, data_type: str = "text") -> Optional[Dict[str, Any]]:
        if not self.page:
            return None
        try:
            if data_type == "links":
                links = await self.page.evaluate("""
                    Array.from(document.querySelectorAll('a'))
                      .map(a => ({url: a.href || '', text: (a.textContent || '').trim()}))
                """)
                return {"links": links, "count": len(links)}
            if data_type == "images":
                images = await self.page.evaluate("""
                    Array.from(document.querySelectorAll('img'))
                      .map(img => ({src: img.src || '', alt: img.alt || ''}))
                """)
                return {"images": images, "count": len(images)}
            if data_type == "forms":
                forms = await self.page.evaluate("""
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
                """)
                return {"forms": forms, "count": len(forms)}
            title = await self.page.title()
            url = self.page.url
            text = await self.page.evaluate("document.body && document.body.innerText || ''")
            return {"text": text, "title": title, "url": url}
        except Exception as e:
            logger.error(f"extract_data({data_type}) failed: {e}")
            return None

    # ---------- Intent mapping ----------
    def _intent_to_action(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate the classic {intent, parameters} shape to a normalized action dict.
        """
        if "type" in intent:
            return intent

        t = (intent.get("intent") or "").upper()
        p = intent.get("parameters") or {}

        if t == "NAVIGATE":
            return {"type": "NAVIGATE", "url": p.get("target") or "about:blank"}
        if t == "SEARCH":
            return {"type": "SEARCH", "text": p.get("text", ""), "selector": p.get("selector"), "scope": p.get("scope")}
        if t == "CLICK":
            # selector may be a human phrase; we’ll resolve it
            return {"type": "CLICK", "selector": p.get("selector") or "", "scope": p.get("scope")}
        if t == "TYPE":
            return {"type": "TYPE", "selector": p.get("selector"), "text": p.get("text", "")}
        if t == "SCROLL":
            direction = (p.get("direction") or "down").lower()
            amount = 800 if direction == "down" else -800
            return {"type": "SCROLL", "x": 0, "y": amount}
        if t == "PRESS":
            return {"type": "PRESS", "key": p.get("key", "Enter")}
        if t == "EXTRACT":
            return {"type": "EXTRACT", "selector": p.get("selector") or "body"}
        if t == "WAIT":
            return {"type": "WAIT", "ms": int(p.get("timeout", 1)) * 1000}
        if t == "UPLOAD":
            return {"type": "UPLOAD", "selector": p.get("selector") or "", "file": p.get("file_path") or ""}
        if t == "DOWNLOAD":
            return {"type": "DOWNLOAD", "selector": p.get("selector") or ""}
        if t == "SCREENSHOT":
            return {"type": "SCREENSHOT"}
        return {"type": "NOOP"}

    # ---------- High-level executor ----------
    async def execute_command(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a high-level intent via Playwright. Auto-screenshot after NAVIGATE.
        """
        action = self._intent_to_action(intent)

        # Ensure session + page ready
        if not self.session_id:
            await self.start_session()
        if not self.page:
            raise RuntimeError("Playwright page is not ready")

        async with self._action_lock:
            try:
                t = action.get("type")

                if t == "NAVIGATE":
                    url = action["url"]
                    await self.page.goto(url, wait_until="domcontentloaded")
                    # give dynamic pages a moment, then settle
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    shot = await self._autosshot()
                    return {"success": True, "action": action, "screenshot_path": shot}

                if t == "SCREENSHOT":
                    png = await self.take_screenshot()
                    return {"success": True, "action": action, "screenshot": bool(png)}

                if t == "SEARCH":
                    query = (action.get("text") or "").strip()
                    if not query:
                        return {"success": False, "error": "SEARCH requires 'text'."}

                    url = (self.page.url or "").lower()
                    sel = self._pick_search_selector(url, action.get("selector"))

                    try:
                        # Use on-page search box if present
                        if await self.wait_for_element(sel, timeout=5):
                            try:
                                await self.page.fill(sel, "")
                            except Exception:
                                pass
                            await self.page.type(sel, query, delay=20)
                            await self.page.keyboard.press("Enter")

                            # Site-specific waits
                            if "youtube.com" in url:
                                await self.page.wait_for_selector(
                                    "ytd-video-renderer,ytd-rich-item-renderer,ytd-item-section-renderer",
                                    timeout=15000
                                )
                            elif "google." in url:
                                await self.page.wait_for_selector("#search,div#rso,div.g", timeout=15000)
                            else:
                                try:
                                    await self.page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception:
                                    pass

                            shot = await self._autosshot()
                            return {"success": True, "action": action, "screenshot_path": shot}

                        # Fallback: perform a Google search
                        import urllib.parse as _u
                        q = _u.quote(query)
                        await self.page.goto(f"https://www.google.com/search?q={q}", wait_until="domcontentloaded")
                        await self.page.wait_for_selector("#search,div#rso,div.g", timeout=15000)
                        shot = await self._autosshot()
                        return {"success": True, "action": action, "screenshot_path": shot}

                    except Exception as e:
                        logger.exception("SEARCH failed")
                        return {"success": False, "error": f"SEARCH failed: {e}", "action": action}

                if t == "CLICK":
                    raw_sel = (action.get("selector") or "").strip()
                    scope = action.get("scope")

                    # Heuristic: if looks like CSS (contains . # [ ] : etc), try direct; else treat as phrase
                    looks_like_css = bool(re.search(r"[#.\[\]:>,=]|^//|^\(//", raw_sel))
                    if looks_like_css:
                        try:
                            await self.page.wait_for_selector(raw_sel, timeout=8000)
                            await self.page.click(raw_sel, timeout=8000)
                            return {"success": True, "action": action, "via": "css"}
                        except Exception as e:
                            logger.info(f"Direct CSS click failed, falling back to phrase resolver: {e}")

                    ok, dbg = await self._click_by_phrase(raw_sel or "OK", scope_hint=scope, hover_first=True)
                    if ok:
                        return {"success": True, "action": action, "via": "phrase", "debug": dbg}
                    return {"success": False, "error": f"CLICK failed: {dbg}", "action": action}

                if t == "TYPE":
                    sel = (action.get("selector") or "").strip()
                    text = action.get("text", "")
                    if sel:
                        try:
                            await self.page.wait_for_selector(sel, timeout=8000)
                            try:
                                await self.page.fill(sel, "")
                            except Exception:
                                pass
                            await self.page.type(sel, text, delay=20)
                            return {"success": True, "action": action}
                        except Exception as e:
                            # Fall back to focusing a field by phrase
                            ok, dbg = await self._click_by_phrase(sel, hover_first=False)
                            if ok:
                                await self.page.keyboard.type(text, delay=20)
                                return {"success": True, "action": action, "via": "phrase-focus"}
                            return {"success": False, "error": f"TYPE failed: {e}", "action": action}
                    else:
                        await self.page.keyboard.type(text, delay=20)
                        return {"success": True, "action": action}

                if t == "SCROLL":
                    y = int(action.get("y", 800))
                    await self.page.evaluate("window.scrollBy(0, arguments[0])", y)
                    return {"success": True, "action": action}

                if t == "PRESS":
                    key = action.get("key", "Enter")
                    await self.page.keyboard.press(key)
                    return {"success": True, "action": action}

                if t == "EXTRACT":
                    title = await self.page.title()
                    url = self.page.url
                    text = await self.page.evaluate("document.body && document.body.innerText || ''")
                    return {"success": True, "action": action, "data": {"title": title, "url": url, "text": text}}

                if t == "WAIT":
                    ms = int(action.get("ms", 1000))
                    await asyncio.sleep(ms / 1000.0)
                    return {"success": True, "action": action}

                if t == "UPLOAD":
                    sel = action.get("selector") or ""
                    path = action.get("file") or ""
                    if not (sel and path):
                        return {"success": False, "error": "UPLOAD requires 'selector' and 'file' path."}
                    await self.page.set_input_files(sel, path)
                    return {"success": True, "action": action}

                if t == "DOWNLOAD":
                    sel = action.get("selector") or ""
                    if not sel:
                        return {"success": False, "error": "DOWNLOAD requires 'selector'."}
                    async with self.page.expect_download() as dl_info:
                        await self.page.click(sel)
                    download = await dl_info.value
                    path = await download.path()
                    return {"success": True, "action": action, "download_path": str(path)}

                if t == "NOOP":
                    return {"success": False, "error": "NOOP (no actionable command parsed).", "action": action}

                return {"success": False, "error": f"Unknown action {t}", "action": action}

            except Exception as e:
                logger.exception("execute_command error")
                return {"success": False, "error": str(e), "action": action}

    async def execute_workflow(self, intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i, intent in enumerate(intents, start=1):
            logger.info(f"Executing step {i}/{len(intents)}: {intent.get('intent') or intent.get('type', 'UNKNOWN')}")
            result = await self.execute_command(intent)
            results.append({
                "step": i,
                "intent": intent,
                "result": result,
                "success": bool(result.get("success")),
            })
            await asyncio.sleep(0.2)
        logger.info(f"Workflow completed: {len(results)} steps executed")
        return results


# ---------- Convenience runner ----------
async def run_workflow(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    async with BrowserAutomation() as b:
        await b.start_session()
        return await b.execute_workflow(intents)
