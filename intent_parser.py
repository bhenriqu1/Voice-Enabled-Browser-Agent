"""
Intent parser module that converts natural speech to structured browser commands
"""
import json
import logging
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)


class IntentParser:
    """Converts natural language to structured browser commands using GPT-5"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for intent parsing"""
        return """
You are an expert intent parser that converts natural language voice commands into structured JSON instructions for browser automation.

Your task is to analyze voice transcriptions and convert them into precise, actionable browser commands.

Available command types:
1. NAVIGATE - Navigate to a URL
2. SEARCH - Search for something on a website
3. CLICK - Click on an element (button, link, etc.)
4. TYPE - Type text into an input field
5. EXTRACT - Extract data from the page
6. SCROLL - Scroll up/down on the page
7. WAIT - Wait for a specific condition
8. SCREENSHOT - Take a screenshot
9. FILTER - Filter or sort content
10. FILL_FORM - Fill out a form with multiple fields
11. DOWNLOAD - Download a file
12. UPLOAD - Upload a file

Response format (JSON):
{
    "intent": "COMMAND_TYPE",
    "confidence": 0.95,
    "parameters": {
        "target": "specific element or URL",
        "text": "text to type or search for",
        "selector": "CSS selector or description",
        "wait_condition": "condition to wait for",
        "data_type": "type of data to extract",
        "form_data": {"field1": "value1", "field2": "value2"}
    },
    "context": "additional context or clarification needed",
    "follow_up": ["potential next steps or related commands"]
}

Examples:
- "Go to Google" → {"intent": "NAVIGATE", "parameters": {"target": "https://google.com"}}
- "Search for Python tutorials" → {"intent": "SEARCH", "parameters": {"text": "Python tutorials"}}
- "Click the login button" → {"intent": "CLICK", "parameters": {"selector": "login button"}}
- "Type my email address" → {"intent": "TYPE", "parameters": {"text": "user@example.com", "selector": "email input"}}
- "Extract all the product prices" → {"intent": "EXTRACT", "parameters": {"data_type": "prices"}}
- "Scroll down to see more results" → {"intent": "SCROLL", "parameters": {"direction": "down"}}
- "Fill out the contact form with my name and email" → {"intent": "FILL_FORM", "parameters": {"form_data": {"name": "user input", "email": "user input"}}}

Always respond with valid JSON only. If the command is unclear or ambiguous, set confidence low and provide context about what clarification is needed.
"""
    
    async def parse_intent(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Parse voice transcript into structured intent"""
        try:
            # Prepare the conversation
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Voice command: '{transcript}'"}
            ]
            
            # Add context if provided
            if context:
                messages.append({
                    "role": "assistant", 
                    "content": f"Current context: {json.dumps(context, indent=2)}"
                })
                messages.append({
                    "role": "user", 
                    "content": "Please consider this context when parsing the intent."
                })
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",  # Using GPT-4 as GPT-5 is not available yet
                messages=messages,
                temperature=0.1,
                max_tokens=500
            )
            
            # Parse the response
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            try:
                intent_data = json.loads(content)
                logger.info(f"Parsed intent: {intent_data}")
                return intent_data
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract JSON from the response
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    intent_data = json.loads(json_str)
                    logger.info(f"Parsed intent (extracted): {intent_data}")
                    return intent_data
                else:
                    raise ValueError("No valid JSON found in response")
        
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return {
                "intent": "ERROR",
                "confidence": 0.0,
                "parameters": {},
                "context": f"Failed to parse intent: {str(e)}",
                "follow_up": []
            }
    
    async def parse_multi_step_intent(self, transcript: str, context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Parse complex multi-step commands into a sequence of intents"""
        try:
            multi_step_prompt = f"""
Parse this complex voice command into a sequence of individual browser actions:

Voice command: "{transcript}"

Return a JSON array of intents, where each intent follows the same format as single intents.
Break down complex workflows into logical steps.

Example:
"Search for laptops on Amazon, filter by price under $1000, and add the first result to cart"
→ [
    {{"intent": "NAVIGATE", "parameters": {{"target": "https://amazon.com"}}}},
    {{"intent": "SEARCH", "parameters": {{"text": "laptops"}}}},
    {{"intent": "FILTER", "parameters": {{"filter_type": "price", "max_value": 1000}}}},
    {{"intent": "CLICK", "parameters": {{"selector": "first search result"}}}},
    {{"intent": "CLICK", "parameters": {{"selector": "add to cart button"}}}}
]
"""
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": multi_step_prompt}
            ]
            
            if context:
                messages.append({
                    "role": "assistant", 
                    "content": f"Current context: {json.dumps(context, indent=2)}"
                })
            
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON array
            json_start = content.find('[')
            json_end = content.rfind(']') + 1
            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                intents = json.loads(json_str)
                logger.info(f"Parsed multi-step intents: {len(intents)} steps")
                return intents
            else:
                # Fallback to single intent
                single_intent = await self.parse_intent(transcript, context)
                return [single_intent]
        
        except Exception as e:
            logger.error(f"Error parsing multi-step intent: {e}")
            return [{
                "intent": "ERROR",
                "confidence": 0.0,
                "parameters": {},
                "context": f"Failed to parse multi-step intent: {str(e)}",
                "follow_up": []
            }]
    
    def validate_intent(self, intent_data: Dict[str, Any]) -> bool:
        """Validate that the parsed intent has required fields"""
        required_fields = ["intent", "confidence", "parameters"]
        return all(field in intent_data for field in required_fields)
    
    def get_intent_summary(self, intent_data: Dict[str, Any]) -> str:
        """Get a human-readable summary of the intent"""
        intent = intent_data.get("intent", "UNKNOWN")
        confidence = intent_data.get("confidence", 0.0)
        parameters = intent_data.get("parameters", {})
        
        summary = f"Intent: {intent} (confidence: {confidence:.2f})"
        
        if parameters:
            key_params = []
            for key, value in parameters.items():
                if value and key in ["target", "text", "selector", "data_type"]:
                    key_params.append(f"{key}: {value}")
            
            if key_params:
                summary += f" - {', '.join(key_params)}"
        
        return summary
