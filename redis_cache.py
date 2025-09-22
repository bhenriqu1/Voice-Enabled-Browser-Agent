"""
Redis cache module for maintaining conversation context and state
"""
import json
import logging
from typing import Dict, List, Optional, Any
import redis.asyncio as redis
from datetime import datetime, timedelta
from config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-based cache for maintaining conversation context and state"""
    
    def __init__(self):
        self.redis_client = None
        self.session_id = None
        self.ttl = 3600  # 1 hour TTL for session data
    
    async def connect(self) -> None:
        """Connect to Redis server"""
        try:
            # Only pass password if it's configured
            connection_params = {
                "decode_responses": True
            }
            if settings.redis_password:
                connection_params["password"] = settings.redis_password
            
            self.redis_client = redis.from_url(
                settings.redis_url,
                **connection_params
            )
            # Test connection
            await self.redis_client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Disconnected from Redis")
    
    def set_session_id(self, session_id: str) -> None:
        """Set the current session ID"""
        self.session_id = session_id
    
    def _get_key(self, key: str) -> str:
        """Get the full Redis key with session prefix"""
        return f"voice_browser_agent:{self.session_id}:{key}"
    
    async def store_conversation_turn(self, turn_data: Dict[str, Any]) -> None:
        """Store a conversation turn in Redis"""
        try:
            if not self.session_id:
                raise ValueError("Session ID not set")
            
            turn_id = turn_data.get("turn_id", f"turn_{datetime.now().timestamp()}")
            key = self._get_key(f"conversation:{turn_id}")
            
            # Add timestamp
            turn_data["timestamp"] = datetime.now().isoformat()
            
            await self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(turn_data)
            )
            
            # Add to conversation list
            await self.redis_client.lpush(
                self._get_key("conversation_list"),
                turn_id
            )
            
            # Trim list to last 50 turns
            await self.redis_client.ltrim(
                self._get_key("conversation_list"),
                0,
                49
            )
            
            logger.info(f"Stored conversation turn: {turn_id}")
        
        except Exception as e:
            logger.error(f"Error storing conversation turn: {e}")
    
    async def get_conversation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        try:
            if not self.session_id:
                return []
            
            # Get turn IDs
            turn_ids = await self.redis_client.lrange(
                self._get_key("conversation_list"),
                0,
                limit - 1
            )
            
            # Get turn data
            turns = []
            for turn_id in turn_ids:
                key = self._get_key(f"conversation:{turn_id}")
                turn_data = await self.redis_client.get(key)
                if turn_data:
                    turns.append(json.loads(turn_data))
            
            return turns
        
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    async def store_browser_state(self, state: Dict[str, Any]) -> None:
        """Store current browser state"""
        try:
            if not self.session_id:
                raise ValueError("Session ID not set")
            
            key = self._get_key("browser_state")
            state["timestamp"] = datetime.now().isoformat()
            
            await self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(state)
            )
            
            logger.info("Stored browser state")
        
        except Exception as e:
            logger.error(f"Error storing browser state: {e}")
    
    async def get_browser_state(self) -> Optional[Dict[str, Any]]:
        """Get current browser state"""
        try:
            if not self.session_id:
                return None
            
            key = self._get_key("browser_state")
            state_data = await self.redis_client.get(key)
            
            if state_data:
                return json.loads(state_data)
            return None
        
        except Exception as e:
            logger.error(f"Error getting browser state: {e}")
            return None
    
    async def store_intent_context(self, context: Dict[str, Any]) -> None:
        """Store intent parsing context"""
        try:
            if not self.session_id:
                raise ValueError("Session ID not set")
            
            key = self._get_key("intent_context")
            context["timestamp"] = datetime.now().isoformat()
            
            await self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(context)
            )
            
            logger.info("Stored intent context")
        
        except Exception as e:
            logger.error(f"Error storing intent context: {e}")
    
    async def get_intent_context(self) -> Optional[Dict[str, Any]]:
        """Get intent parsing context"""
        try:
            if not self.session_id:
                return None
            
            key = self._get_key("intent_context")
            context_data = await self.redis_client.get(key)
            
            if context_data:
                return json.loads(context_data)
            return None
        
        except Exception as e:
            logger.error(f"Error getting intent context: {e}")
            return None
    
    async def store_extracted_data(self, data: Dict[str, Any], data_type: str) -> None:
        """Store extracted data from browser"""
        try:
            if not self.session_id:
                raise ValueError("Session ID not set")
            
            key = self._get_key(f"extracted_data:{data_type}")
            data["timestamp"] = datetime.now().isoformat()
            data["data_type"] = data_type
            
            await self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(data)
            )
            
            # Add to data list
            await self.redis_client.lpush(
                self._get_key("extracted_data_list"),
                f"{data_type}:{datetime.now().timestamp()}"
            )
            
            logger.info(f"Stored extracted data: {data_type}")
        
        except Exception as e:
            logger.error(f"Error storing extracted data: {e}")
    
    async def get_extracted_data(self, data_type: str) -> Optional[Dict[str, Any]]:
        """Get extracted data by type"""
        try:
            if not self.session_id:
                return None
            
            key = self._get_key(f"extracted_data:{data_type}")
            data = await self.redis_client.get(key)
            
            if data:
                return json.loads(data)
            return None
        
        except Exception as e:
            logger.error(f"Error getting extracted data: {e}")
            return None
    
    async def store_workflow_state(self, workflow_id: str, state: Dict[str, Any]) -> None:
        """Store multi-step workflow state"""
        try:
            if not self.session_id:
                raise ValueError("Session ID not set")
            
            key = self._get_key(f"workflow:{workflow_id}")
            state["timestamp"] = datetime.now().isoformat()
            state["workflow_id"] = workflow_id
            
            await self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(state)
            )
            
            logger.info(f"Stored workflow state: {workflow_id}")
        
        except Exception as e:
            logger.error(f"Error storing workflow state: {e}")
    
    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow state"""
        try:
            if not self.session_id:
                return None
            
            key = self._get_key(f"workflow:{workflow_id}")
            state_data = await self.redis_client.get(key)
            
            if state_data:
                return json.loads(state_data)
            return None
        
        except Exception as e:
            logger.error(f"Error getting workflow state: {e}")
            return None
    
    async def clear_session(self) -> None:
        """Clear all data for current session"""
        try:
            if not self.session_id:
                return
            
            # Get all keys for this session
            pattern = self._get_key("*")
            keys = await self.redis_client.keys(pattern)
            
            if keys:
                await self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} keys for session {self.session_id}")
        
        except Exception as e:
            logger.error(f"Error clearing session: {e}")
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        try:
            if not self.session_id:
                return {}
            
            pattern = self._get_key("*")
            keys = await self.redis_client.keys(pattern)
            
            # Count different types of data
            stats = {
                "total_keys": len(keys),
                "conversation_turns": 0,
                "extracted_data_types": 0,
                "workflows": 0
            }
            
            for key in keys:
                if "conversation:" in key:
                    stats["conversation_turns"] += 1
                elif "extracted_data:" in key:
                    stats["extracted_data_types"] += 1
                elif "workflow:" in key:
                    stats["workflows"] += 1
            
            return stats
        
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {}
