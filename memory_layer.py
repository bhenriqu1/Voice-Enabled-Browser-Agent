"""
Memory layer module using Mem0 for persistent context management
"""
import logging
from typing import Dict, List, Optional, Any
from mem0 import Memory
from config import settings
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryLayer:
    """Memory layer using Mem0 for persistent context and knowledge management"""

    def __init__(self):
        # Minimal, v1-style dict config (LLM + embedder). You can add vector_store later.
        self.memory = Memory.from_config({
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "api_key": settings.openai_api_key,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": settings.openai_api_key,
                },
            },
        })
        # We’ll use Mem0’s run_id to represent your per-session context
        self.session_id: Optional[str] = None

    def set_session_id(self, session_id: str) -> None:
        self.session_id = session_id

    async def store_conversation_memory(self, transcript: str, intent: Dict[str, Any], result: Dict[str, Any]) -> str:
        try:
            memory_data = {
                "transcript": transcript,
                "intent": intent.get("intent", ""),
                "confidence": intent.get("confidence", 0.0),
                "parameters": intent.get("parameters", {}),
                "result_success": result.get("success", False),
                "result_data": result.get("data", {}),
                "session_id": self.session_id,
                "timestamp": self._now(),
            }

            memory_id = self.memory.add(
                messages=[{"role": "user", "content": transcript}],
                user_id="default",                # or your real user id
                run_id=self.session_id,           # tie to this session
                metadata=memory_data,
            )
            logger.info(f"Stored conversation memory: {memory_id}")
            return memory_id or ""
        except Exception as e:
            logger.error(f"Error storing conversation memory: {e}")
            return ""

    async def store_browser_context(self, url: str, page_title: str, extracted_data: Optional[Dict] = None) -> str:
        try:
            context_data = {
                "url": url,
                "page_title": page_title,
                "extracted_data": extracted_data or {},
                "session_id": self.session_id,
                "timestamp": self._now(),
            }

            memory_id = self.memory.add(
                messages=[{"role": "assistant", "content": f"Browser context: {page_title} at {url}"}],
                user_id="default",
                run_id=self.session_id,
                metadata=context_data,
            )
            logger.info(f"Stored browser context: {memory_id}")
            return memory_id or ""
        except Exception as e:
            logger.error(f"Error storing browser context: {e}")
            return ""

    async def store_user_preferences(self, preferences: Dict[str, Any]) -> str:
        try:
            memory_id = self.memory.add(
                messages=[{"role": "user", "content": f"User preferences: {preferences}"}],
                user_id="default",
                run_id=self.session_id,
                metadata={
                    "preferences": preferences,
                    "session_id": self.session_id,
                    "timestamp": self._now(),
                    "category": "preferences",
                },
            )
            logger.info(f"Stored user preferences: {memory_id}")
            return memory_id or ""
        except Exception as e:
            logger.error(f"Error storing user preferences: {e}")
            return ""

    async def store_workflow_memory(self, workflow_name: str, steps: List[Dict[str, Any]], result: Dict[str, Any]) -> str:
        try:
            workflow_data = {
                "workflow_name": workflow_name,
                "steps": steps,
                "result": result,
                "step_count": len(steps),
                "session_id": self.session_id,
                "timestamp": self._now(),
            }

            memory_id = self.memory.add(
                messages=[{"role": "assistant", "content": f"Workflow '{workflow_name}' completed with {len(steps)} steps"}],
                user_id="default",
                run_id=self.session_id,
                metadata=workflow_data,
            )
            logger.info(f"Stored workflow memory: {memory_id}")
            return memory_id or ""
        except Exception as e:
            logger.error(f"Error storing workflow memory: {e}")
            return ""

    async def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            if not query or not query.strip():
                # Return empty list for empty queries instead of causing API error
                return []
            
            # Use the correct API format for Mem0 search
            res = self.memory.search(
                query=query, 
                user_id="default", 
                run_id=self.session_id, 
                limit=limit
            )
            
            # Handle different response formats
            if isinstance(res, dict):
                results = res.get("results", [])
            elif isinstance(res, list):
                results = res
            else:
                results = []
            
            formatted = []
            for r in results:
                if isinstance(r, dict):
                    formatted.append({
                        "id": r.get("id", ""),
                        "message": r.get("memory", "") or r.get("message", ""),
                        "metadata": r.get("metadata", {}),
                        "score": r.get("score", 0.0),
                    })
            
            logger.info(f"Found {len(formatted)} memories for query: {query}")
            return formatted
        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            return []

    async def get_conversation_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            return await self.search_memories("conversation transcript intent", limit=limit)
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return []

    async def get_browser_context(self) -> Optional[Dict[str, Any]]:
        try:
            results = await self.search_memories("browser context page_title url", limit=1)
            return results[0].get("metadata", {}) if results else None
        except Exception as e:
            logger.error(f"Error getting browser context: {e}")
            return None

    async def get_user_preferences(self) -> Dict[str, Any]:
        try:
            results = await self.search_memories("preferences", limit=1)
            if results:
                md = results[0].get("metadata", {})
                return md.get("preferences", {})
            return {}
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return {}

    async def get_workflow_examples(self, workflow_type: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            query = "workflow steps" if not workflow_type else f"workflow {workflow_type}"
            results = await self.search_memories(query, limit=5)
            return [r.get("metadata", {}) for r in results if "workflow_name" in r.get("metadata", {})]
        except Exception as e:
            logger.error(f"Error getting workflow examples: {e}")
            return []

    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        try:
            # Mem0 now has update in the SDK for platform; OSS exposes update() too in v1 docs.
            self.memory.update(memory_id=memory_id, data=updates.get("text") or updates)
            return True
        except Exception as e:
            logger.error(f"Error updating memory: {e}")
            return False

    async def delete_memory(self, memory_id: str) -> bool:
        try:
            self.memory.delete(memory_id=memory_id)
            return True
        except Exception as e:
            logger.error(f"Error deleting memory: {e}")
            return False

    async def get_memory_stats(self) -> Dict[str, Any]:
        try:
            all_memories = await self.search_memories("", limit=100)
            stats = {"total_memories": len(all_memories), "conversation_memories": 0, "browser_contexts": 0, "workflows": 0, "preferences": 0}
            for m in all_memories:
                md = m.get("metadata", {})
                if "transcript" in md:
                    stats["conversation_memories"] += 1
                elif "url" in md:
                    stats["browser_contexts"] += 1
                elif "workflow_name" in md:
                    stats["workflows"] += 1
                elif "preferences" in md:
                    stats["preferences"] += 1
            return stats
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
            return {}

    def _now(self) -> str:
        return datetime.now().isoformat()

    async def clear_session_memories(self) -> bool:
        try:
            all_memories = await self.search_memories("", limit=1000)
            for m in all_memories:
                mid = m.get("id")
                if mid:
                    await self.delete_memory(mid)
            logger.info(f"Cleared {len(all_memories)} memories for session {self.session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing session memories: {e}")
            return False
