"""
FastAPI web interface for the Voice Browser Agent
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import base64
from datetime import datetime

from voice_browser_agent import VoiceBrowserAgent
from voice_input import transcribe_audio_file
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Voice-Enabled Browser Agent",
    description="AI-powered browser automation with voice control",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: Optional[VoiceBrowserAgent] = None
active_connections: Dict[str, WebSocket] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup"""
    global agent
    agent = VoiceBrowserAgent()
    await agent.initialize()
    logger.info("Voice Browser Agent initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global agent
    if agent:
        await agent.cleanup()
    logger.info("Voice Browser Agent shutdown")


@app.get("/")
async def get_homepage():
    """Serve the main HTML page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Voice Browser Agent</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                margin: 0;
                font-size: 2.5em;
                font-weight: 300;
            }
            .header p {
                margin: 10px 0 0 0;
                font-size: 1.2em;
                opacity: 0.9;
            }
            .content {
                padding: 30px;
            }
            .voice-controls {
                text-align: center;
                margin-bottom: 30px;
            }
            .voice-button {
                background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                color: white;
                border: none;
                padding: 20px 40px;
                font-size: 1.2em;
                border-radius: 50px;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 5px 15px rgba(255, 107, 107, 0.4);
            }
            .voice-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(255, 107, 107, 0.6);
            }
            .voice-button:active {
                transform: translateY(0);
            }
            .voice-button.listening {
                background: linear-gradient(135deg, #00b894 0%, #00a085 100%);
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            .status {
                text-align: center;
                margin: 20px 0;
                padding: 15px;
                border-radius: 10px;
                background: #f8f9fa;
                border-left: 4px solid #4facfe;
            }
            .conversation {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
                max-height: 400px;
                overflow-y: auto;
            }
            .message {
                margin: 10px 0;
                padding: 15px;
                border-radius: 10px;
                max-width: 80%;
            }
            .user-message {
                background: #4facfe;
                color: white;
                margin-left: auto;
            }
            .agent-message {
                background: #e9ecef;
                color: #333;
            }
            .screenshot {
                max-width: 100%;
                border-radius: 10px;
                margin: 10px 0;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                text-align: center;
            }
            .stat-number {
                font-size: 2em;
                font-weight: bold;
                color: #4facfe;
            }
            .stat-label {
                color: #666;
                margin-top: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎤 Voice Browser Agent</h1>
                <p>Control your browser with natural voice commands</p>
            </div>
            <div class="content">
                <div class="voice-controls">
                    <button id="voiceButton" class="voice-button">🎤 Start Listening</button>
                    <div id="status" class="status">Ready to listen...</div>
                </div>
                
                <div class="stats" id="stats">
                    <!-- Stats will be populated here -->
                </div>
                
                <div class="conversation" id="conversation">
                    <div class="message agent-message">
                        <strong>Agent:</strong> Hello! I'm your voice-enabled browser assistant. 
                        You can ask me to navigate to websites, search for information, fill out forms, 
                        extract data, and much more. Just click the microphone button and start speaking!
                    </div>
                </div>
            </div>
        </div>

        <script>
            let isListening = false;
            let mediaRecorder;
            let audioChunks = [];
            let ws;

            // WebSocket connection
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
                
                ws.onopen = function(event) {
                    console.log('WebSocket connected');
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    handleWebSocketMessage(data);
                };
                
                ws.onclose = function(event) {
                    console.log('WebSocket disconnected');
                    setTimeout(connectWebSocket, 1000);
                };
            }

            // Handle WebSocket messages
            function handleWebSocketMessage(data) {
                if (data.type === 'transcript') {
                    addMessage('user', data.transcript);
                } else if (data.type === 'response') {
                    addMessage('agent', data.message);
                } else if (data.type === 'screenshot') {
                    addScreenshot(data.screenshot);
                } else if (data.type === 'status') {
                    updateStatus(data.message);
                } else if (data.type === 'stats') {
                    updateStats(data.stats);
                }
            }

            // Add message to conversation
            function addMessage(sender, message) {
                const conversation = document.getElementById('conversation');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}-message`;
                messageDiv.innerHTML = `<strong>${sender === 'user' ? 'You' : 'Agent'}:</strong> ${message}`;
                conversation.appendChild(messageDiv);
                conversation.scrollTop = conversation.scrollHeight;
            }

            // Add screenshot to conversation
            function addScreenshot(screenshotData) {
                const conversation = document.getElementById('conversation');
                const screenshotDiv = document.createElement('div');
                screenshotDiv.innerHTML = `<img src="data:image/png;base64,${screenshotData}" class="screenshot" alt="Screenshot">`;
                conversation.appendChild(screenshotDiv);
                conversation.scrollTop = conversation.scrollHeight;
            }

            // Update status
            function updateStatus(message) {
                document.getElementById('status').textContent = message;
            }

            // Update stats
            function updateStats(stats) {
                const statsDiv = document.getElementById('stats');
                statsDiv.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-number">${stats.conversation_turns || 0}</div>
                        <div class="stat-label">Conversation Turns</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${stats.redis_stats?.total_keys || 0}</div>
                        <div class="stat-label">Cached Items</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${stats.memory_stats?.total_memories || 0}</div>
                        <div class="stat-label">Memories</div>
                    </div>
                `;
            }

            // Voice button click handler
            document.getElementById('voiceButton').addEventListener('click', function() {
                if (isListening) {
                    stopListening();
                } else {
                    startListening();
                }
            });

            // Start listening
            async function startListening() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

                    mediaRecorder.ondataavailable = function(event) {
                        audioChunks.push(event.data);
                    };

                    mediaRecorder.onstop = function() {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        sendAudio(audioBlob);
                        stream.getTracks().forEach(track => track.stop());
                    };

                    mediaRecorder.start();
                    isListening = true;
                    document.getElementById('voiceButton').textContent = '🛑 Stop Listening';
                    document.getElementById('voiceButton').classList.add('listening');
                    updateStatus('Listening... Speak now!');

                } catch (error) {
                    console.error('Error accessing microphone:', error);
                    updateStatus('Error accessing microphone. Please check permissions.');
                }
            }

            // Stop listening
            function stopListening() {
                if (mediaRecorder && isListening) {
                    mediaRecorder.stop();
                    isListening = false;
                    document.getElementById('voiceButton').textContent = '🎤 Start Listening';
                    document.getElementById('voiceButton').classList.remove('listening');
                    updateStatus('Processing...');
                }
            }

            // Send audio to server
            function sendAudio(audioBlob) {
                const formData = new FormData();
                formData.append('audio', audioBlob, 'audio.wav');
                
                fetch('/transcribe', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.transcript) {
                        // Send transcript via WebSocket
                        ws.send(JSON.stringify({
                            type: 'transcript',
                            transcript: data.transcript
                        }));
                    }
                    updateStatus('Ready to listen...');
                })
                .catch(error => {
                    console.error('Error transcribing audio:', error);
                    updateStatus('Error processing audio. Please try again.');
                });
            }

            // Connect WebSocket on page load
            connectWebSocket();

            // Request microphone permission on page load
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(() => {
                    updateStatus('Ready to listen...');
                })
                .catch(() => {
                    updateStatus('Microphone access required. Please allow microphone access.');
                });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    connection_id = str(datetime.now().timestamp())
    active_connections[connection_id] = websocket
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "transcript":
                transcript = message.get("transcript", "")
                if transcript and agent:
                    # Process the transcript
                    await agent.process_voice_input(transcript)
            
    except WebSocketDisconnect:
        del active_connections[connection_id]
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe uploaded audio file"""
    try:
        audio_data = await audio.read()
        transcript = await transcribe_audio_file(audio_data)
        
        return JSONResponse({
            "transcript": transcript,
            "success": True
        })
    
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return JSONResponse({
            "transcript": "",
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/command")
async def execute_command(command: dict):
    """Execute a browser command directly"""
    try:
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        # Process the command
        await agent.process_voice_input(command.get("text", ""))
        
        return JSONResponse({
            "success": True,
            "message": "Command executed"
        })
    
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.get("/stats")
async def get_stats():
    """Get agent statistics"""
    try:
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        stats = await agent.get_session_stats()
        return JSONResponse(stats)
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return JSONResponse({
            "error": str(e)
        }, status_code=500)


@app.post("/screenshot")
async def take_screenshot():
    """Take a screenshot of the current browser state"""
    try:
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        screenshot = await agent.browser_automation.take_screenshot()
        if screenshot:
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            return JSONResponse({
                "success": True,
                "screenshot": screenshot_b64
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "Failed to take screenshot"
            })
    
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/reset")
async def reset_session():
    """Reset the agent session"""
    try:
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        await agent.cleanup()
        await agent.initialize()
        
        return JSONResponse({
            "success": True,
            "message": "Session reset"
        })
    
    except Exception as e:
        logger.error(f"Error resetting session: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web_interface:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
