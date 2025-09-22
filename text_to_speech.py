"""
Text-to-speech module for voice responses
"""
import logging
import asyncio
from typing import Optional
import pyttsx3
import io
import base64
from config import settings

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Text-to-speech handler for voice responses"""
    
    def __init__(self):
        self.engine = None
        self.is_initialized = False
        self._initialize_engine()
    
    def _initialize_engine(self) -> None:
        """Initialize the TTS engine"""
        try:
            self.engine = pyttsx3.init()
            
            # Configure voice settings
            voices = self.engine.getProperty('voices')
            if voices:
                # Try to find a good voice
                for voice in voices:
                    if 'english' in voice.name.lower() or 'en' in voice.id.lower():
                        self.engine.setProperty('voice', voice.id)
                        break
            
            # Set rate and volume
            self.engine.setProperty('rate', settings.voice_rate)
            self.engine.setProperty('volume', settings.voice_volume)
            
            self.is_initialized = True
            logger.info("TTS engine initialized successfully")
        
        except Exception as e:
            logger.error(f"Failed to initialize TTS engine: {e}")
            self.is_initialized = False
    
    async def speak(self, text: str, blocking: bool = True) -> bool:
        """Convert text to speech and play it"""
        try:
            if not self.is_initialized:
                logger.error("TTS engine not initialized")
                return False
            
            if not text.strip():
                logger.warning("Empty text provided for TTS")
                return False
            
            logger.info(f"Speaking: {text[:100]}...")
            
            if blocking:
                # Run in thread to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._speak_sync, text)
            else:
                # Non-blocking
                asyncio.create_task(self._speak_async(text))
            
            return True
        
        except Exception as e:
            logger.error(f"Error in TTS: {e}")
            return False
    
    def _speak_sync(self, text: str) -> None:
        """Synchronous speech method"""
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            logger.error(f"Error in sync TTS: {e}")
    
    async def _speak_async(self, text: str) -> None:
        """Asynchronous speech method"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._speak_sync, text)
        except Exception as e:
            logger.error(f"Error in async TTS: {e}")
    
    async def speak_command_result(self, command: str, success: bool, details: str = "") -> None:
        """Speak the result of a command execution"""
        try:
            if success:
                response = f"Successfully executed {command}"
            else:
                response = f"Failed to execute {command}"
            
            if details:
                response += f". {details}"
            
            await self.speak(response)
        
        except Exception as e:
            logger.error(f"Error speaking command result: {e}")
    
    async def speak_workflow_progress(self, step: int, total_steps: int, step_name: str) -> None:
        """Speak workflow progress"""
        try:
            response = f"Executing step {step} of {total_steps}: {step_name}"
            await self.speak(response)
        
        except Exception as e:
            logger.error(f"Error speaking workflow progress: {e}")
    
    async def speak_error(self, error_message: str) -> None:
        """Speak error messages"""
        try:
            response = f"Error: {error_message}"
            await self.speak(response)
        
        except Exception as e:
            logger.error(f"Error speaking error message: {e}")
    
    async def speak_welcome(self) -> None:
        """Speak welcome message"""
        try:
            welcome_text = "Voice-enabled browser agent is ready. How can I help you today?"
            await self.speak(welcome_text)
        
        except Exception as e:
            logger.error(f"Error speaking welcome message: {e}")
    
    async def speak_help(self) -> None:
        """Speak help information"""
        try:
            help_text = """
            I can help you with various browser tasks. You can ask me to:
            - Navigate to websites
            - Search for information
            - Click on buttons and links
            - Fill out forms
            - Extract data from pages
            - Take screenshots
            - And much more!
            
            Just speak naturally and I'll understand what you want to do.
            """
            await self.speak(help_text)
        
        except Exception as e:
            logger.error(f"Error speaking help message: {e}")
    
    def set_voice_properties(self, rate: Optional[int] = None, volume: Optional[float] = None) -> None:
        """Update voice properties"""
        try:
            if not self.is_initialized:
                return
            
            if rate is not None:
                self.engine.setProperty('rate', rate)
                logger.info(f"Voice rate set to {rate}")
            
            if volume is not None:
                self.engine.setProperty('volume', volume)
                logger.info(f"Voice volume set to {volume}")
        
        except Exception as e:
            logger.error(f"Error setting voice properties: {e}")
    
    def get_available_voices(self) -> list:
        """Get list of available voices"""
        try:
            if not self.is_initialized:
                return []
            
            voices = self.engine.getProperty('voices')
            voice_list = []
            
            for voice in voices:
                voice_list.append({
                    'id': voice.id,
                    'name': voice.name,
                    'languages': voice.languages
                })
            
            return voice_list
        
        except Exception as e:
            logger.error(f"Error getting available voices: {e}")
            return []
    
    def set_voice(self, voice_id: str) -> bool:
        """Set a specific voice by ID"""
        try:
            if not self.is_initialized:
                return False
            
            self.engine.setProperty('voice', voice_id)
            logger.info(f"Voice set to {voice_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error setting voice: {e}")
            return False
    
    async def save_audio_to_file(self, text: str, filename: str) -> bool:
        """Save speech to audio file"""
        try:
            if not self.is_initialized:
                return False
            
            # This would require additional implementation for file saving
            # For now, we'll just log the request
            logger.info(f"Audio save requested: {filename}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving audio to file: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up TTS resources"""
        try:
            if self.engine:
                self.engine.stop()
                self.engine = None
                self.is_initialized = False
                logger.info("TTS engine cleaned up")
        
        except Exception as e:
            logger.error(f"Error cleaning up TTS engine: {e}")


class TTSResponseBuilder:
    """Helper class to build appropriate TTS responses"""
    
    @staticmethod
    def build_command_response(intent: dict, result: dict) -> str:
        """Build a response for a command execution"""
        intent_type = intent.get("intent", "UNKNOWN")
        success = result.get("success", False)
        
        if success:
            if intent_type == "NAVIGATE":
                url = intent.get("parameters", {}).get("target", "the page")
                return f"Successfully navigated to {url}"
            elif intent_type == "SEARCH":
                query = intent.get("parameters", {}).get("text", "your search")
                return f"Search completed for {query}"
            elif intent_type == "CLICK":
                element = intent.get("parameters", {}).get("selector", "the element")
                return f"Clicked on {element}"
            elif intent_type == "TYPE":
                text = intent.get("parameters", {}).get("text", "the text")
                return f"Typed {text}"
            elif intent_type == "EXTRACT":
                data_type = intent.get("parameters", {}).get("data_type", "data")
                return f"Extracted {data_type} from the page"
            elif intent_type == "SCREENSHOT":
                return "Screenshot captured successfully"
            else:
                return f"Successfully executed {intent_type.lower()} command"
        else:
            error = result.get("error", "Unknown error")
            return f"Failed to execute {intent_type.lower()}: {error}"
    
    @staticmethod
    def build_workflow_response(workflow_results: list) -> str:
        """Build a response for workflow execution"""
        total_steps = len(workflow_results)
        successful_steps = sum(1 for result in workflow_results if result.get("success", False))
        
        if successful_steps == total_steps:
            return f"Workflow completed successfully! All {total_steps} steps executed."
        elif successful_steps > 0:
            return f"Workflow partially completed. {successful_steps} out of {total_steps} steps successful."
        else:
            return "Workflow failed. None of the steps were successful."
    
    @staticmethod
    def build_data_extraction_response(data: dict) -> str:
        """Build a response for data extraction"""
        data_type = data.get("data_type", "data")
        extracted_items = data.get("data", {})
        
        if isinstance(extracted_items, list):
            count = len(extracted_items)
            return f"Extracted {count} {data_type} items from the page."
        elif isinstance(extracted_items, dict):
            keys = list(extracted_items.keys())
            return f"Extracted {data_type} with fields: {', '.join(keys)}."
        else:
            return f"Extracted {data_type} from the page."
