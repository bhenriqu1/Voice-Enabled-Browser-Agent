"""
Main Voice-Enabled Browser Agent orchestrator
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import json

from voice_input import VoiceInputHandler, transcribe_audio_file
from intent_parser import IntentParser
from redis_cache import RedisCache
from browser_automation import BrowserAutomation
from memory_layer import MemoryLayer
from text_to_speech import TextToSpeech, TTSResponseBuilder
from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VoiceBrowserAgent:
    """Main orchestrator for the Voice-Enabled Browser Agent"""
    
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.is_running = False
        
        # Initialize components
        self.voice_input = VoiceInputHandler()
        self.intent_parser = IntentParser()
        self.redis_cache = RedisCache()
        self.browser_automation = BrowserAutomation()
        self.memory_layer = MemoryLayer()
        self.tts = TextToSpeech()
        
        # Set session IDs
        self.redis_cache.set_session_id(self.session_id)
        self.memory_layer.set_session_id(self.session_id)
        
        # Conversation state
        self.conversation_turn = 0
        self.current_workflow = None
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        try:
            logger.info("Initializing Voice Browser Agent...")
            
            # Connect to Redis
            await self.redis_cache.connect()
            
            # Initialize browser session
            await self.browser_automation.start_session()
            
            # Store initial session data
            await self.redis_cache.store_browser_state({
                "session_id": self.session_id,
                "start_time": datetime.now().isoformat(),
                "status": "initialized"
            })
            
            logger.info(f"Agent initialized with session ID: {self.session_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            return False
    
    async def start_voice_session(self) -> None:
        """Start the voice interaction session"""
        try:
            if not self.is_running:
                await self.initialize()
                self.is_running = True
            
            # Welcome message
            await self.tts.speak_welcome()
            
            # Start voice input with callback
            self.voice_input._handle_transcript = self.process_voice_input
            await self.voice_input.start_listening(self.process_voice_input)
        
        except Exception as e:
            logger.error(f"Error starting voice session: {e}")
            await self.tts.speak_error(f"Failed to start voice session: {str(e)}")
    
    async def process_voice_input(self, transcript: str) -> None:
        """Process voice input and execute browser commands"""
        try:
            self.conversation_turn += 1
            logger.info(f"Processing voice input (turn {self.conversation_turn}): {transcript}")
            
            # Store conversation turn
            turn_data = {
                "turn_id": f"turn_{self.conversation_turn}",
                "transcript": transcript,
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id
            }
            await self.redis_cache.store_conversation_turn(turn_data)
            
            # Get conversation context
            context = await self._build_context()
            
            # Parse intent
            intent = await self.intent_parser.parse_intent(transcript, context)
            
            # Validate intent
            if not self.intent_parser.validate_intent(intent):
                await self.tts.speak_error("I didn't understand that command. Please try again.")
                return
            
            # Check if it's a multi-step workflow
            if self._is_workflow_command(intent):
                await self._execute_workflow(transcript, intent, context)
            else:
                await self._execute_single_command(transcript, intent, context)
        
        except Exception as e:
            logger.error(f"Error processing voice input: {e}")
            await self.tts.speak_error(f"Error processing command: {str(e)}")
    
    async def _execute_single_command(self, transcript: str, intent: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Execute a single browser command"""
        try:
            # Execute browser command
            result = await self.browser_automation.execute_command(intent)
            
            # Store result in Redis
            await self.redis_cache.store_conversation_turn({
                "turn_id": f"turn_{self.conversation_turn}_result",
                "intent": intent,
                "result": result,
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id
            })
            
            # Store in memory layer
            await self.memory_layer.store_conversation_memory(transcript, intent, result)
            
            # Generate TTS response
            response = TTSResponseBuilder.build_command_response(intent, result)
            await self.tts.speak(response)
            
            # Take screenshot if successful
            if result.get("success", False):
                screenshot = await self.browser_automation.take_screenshot()
                if screenshot:
                    await self._store_screenshot(screenshot, f"command_{self.conversation_turn}")
            
            # Extract data if requested
            if intent.get("intent") == "EXTRACT":
                data_type = intent.get("parameters", {}).get("data_type", "text")
                extracted_data = await self.browser_automation.extract_data(data_type)
                if extracted_data:
                    await self.redis_cache.store_extracted_data(extracted_data, data_type)
                    await self.memory_layer.store_browser_context(
                        result.get("url", ""),
                        result.get("title", ""),
                        extracted_data
                    )
        
        except Exception as e:
            logger.error(f"Error executing single command: {e}")
            await self.tts.speak_error(f"Command execution failed: {str(e)}")
    
    async def _execute_workflow(self, transcript: str, intent: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Execute a multi-step workflow"""
        try:
            # Parse multi-step intents
            intents = await self.intent_parser.parse_multi_step_intent(transcript, context)
            
            if not intents:
                await self.tts.speak_error("Could not parse workflow steps.")
                return
            
            # Store workflow state
            workflow_id = f"workflow_{self.conversation_turn}"
            self.current_workflow = {
                "id": workflow_id,
                "intents": intents,
                "status": "running",
                "current_step": 0
            }
            
            await self.redis_cache.store_workflow_state(workflow_id, self.current_workflow)
            
            # Execute workflow
            results = await self.browser_automation.execute_workflow(intents)
            
            # Update workflow state
            self.current_workflow["status"] = "completed"
            self.current_workflow["results"] = results
            await self.redis_cache.store_workflow_state(workflow_id, self.current_workflow)
            
            # Store in memory
            await self.memory_layer.store_workflow_memory(
                f"Workflow {workflow_id}",
                intents,
                {"results": results, "success_count": sum(1 for r in results if r.get("success", False))}
            )
            
            # Generate TTS response
            response = TTSResponseBuilder.build_workflow_response(results)
            await self.tts.speak(response)
            
            # Take final screenshot
            screenshot = await self.browser_automation.take_screenshot()
            if screenshot:
                await self._store_screenshot(screenshot, f"workflow_{workflow_id}")
        
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            await self.tts.speak_error(f"Workflow execution failed: {str(e)}")
    
    def _is_workflow_command(self, intent: Dict[str, Any]) -> bool:
        """Check if the command is a multi-step workflow"""
        workflow_keywords = ["and then", "after that", "next", "then", "also", "also do"]
        transcript = intent.get("context", "").lower()
        return any(keyword in transcript for keyword in workflow_keywords)
    
    async def _build_context(self) -> Dict[str, Any]:
        """Build context for intent parsing"""
        try:
            context = {}
            
            # Get conversation history
            history = await self.redis_cache.get_conversation_history(limit=5)
            context["conversation_history"] = history
            
            # Get browser state
            browser_state = await self.redis_cache.get_browser_state()
            context["browser_state"] = browser_state
            
            # Get memory context
            memory_context = await self.memory_layer.get_conversation_context(limit=3)
            context["memory_context"] = memory_context
            
            # Get current page info
            page_content = await self.browser_automation.get_page_content()
            context["current_page"] = page_content
            
            return context
        
        except Exception as e:
            logger.error(f"Error building context: {e}")
            return {}
    
    async def _store_screenshot(self, screenshot_data: bytes, name: str) -> None:
        """Store screenshot data"""
        try:
            # In a real implementation, you'd save this to a file or cloud storage
            # For now, we'll just log it
            logger.info(f"Screenshot captured: {name} ({len(screenshot_data)} bytes)")
        
        except Exception as e:
            logger.error(f"Error storing screenshot: {e}")
    
    async def stop_voice_session(self) -> None:
        """Stop the voice interaction session"""
        try:
            self.is_running = False
            
            # Stop voice input
            await self.voice_input.stop_listening()
            
            # End browser session
            await self.browser_automation.end_session()
            
            # Store final session state
            await self.redis_cache.store_browser_state({
                "session_id": self.session_id,
                "end_time": datetime.now().isoformat(),
                "status": "ended",
                "total_turns": self.conversation_turn
            })
            
            logger.info("Voice session stopped")
        
        except Exception as e:
            logger.error(f"Error stopping voice session: {e}")
    
    async def cleanup(self) -> None:
        """Clean up all resources"""
        try:
            await self.stop_voice_session()
            await self.redis_cache.disconnect()
            self.tts.cleanup()
            logger.info("Agent cleanup completed")
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        try:
            redis_stats = await self.redis_cache.get_session_stats()
            memory_stats = await self.memory_layer.get_memory_stats()
            
            return {
                "session_id": self.session_id,
                "conversation_turns": self.conversation_turn,
                "is_running": self.is_running,
                "redis_stats": redis_stats,
                "memory_stats": memory_stats,
                "current_workflow": self.current_workflow
            }
        
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {}


# CLI interface for testing
async def main():
    """Main function for CLI testing"""
    agent = VoiceBrowserAgent()
    
    try:
        # Initialize agent
        if not await agent.initialize():
            print("Failed to initialize agent")
            return
        
        print(f"Voice Browser Agent started with session ID: {agent.session_id}")
        print("Press Ctrl+C to stop...")
        
        # Start voice session
        await agent.start_voice_session()
        
        # Keep running until interrupted
        while agent.is_running:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        print("\nStopping agent...")
        await agent.cleanup()
        print("Agent stopped.")
    
    except Exception as e:
        print(f"Error: {e}")
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
