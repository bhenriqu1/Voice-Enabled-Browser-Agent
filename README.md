# 🎤 Voice-Enabled Browser Agent

AI-powered browser automation system that listens to natural speech, converts it into structured commands, and executes them in a real browser session. The system leverages speech-to-text, intent parsing, Redis caching, and Browserbase for reliable headless browser automation.

## 🌟 Features

- **Voice Input**: Real-time speech-to-text using Deepgram API
- **Intent Parsing**: GPT-5 powered natural language understanding
- **Browser Automation**: Headless browser control via Browserbase (Stagehand)
- **Context Management**: Redis cache for conversation state
- **Memory Layer**: Mem0 for persistent knowledge storage
- **Text-to-Speech**: Voice responses with pyttsx3
- **Web Interface**: Modern FastAPI web UI
- **Multi-step Workflows**: Complex task automation
- **Data Extraction**: Intelligent content extraction
- **Screenshot Capture**: Visual feedback and documentation

## 🏗️ System Architecture

```
User Voice Input → Deepgram API → Transcription → GPT-5 Intent Parser
                                                      ↓
Redis Cache ← Browser Instructions ← Browserbase API (Stagehand)
     ↓                                    ↓
Mem0 Memory Layer ← Browser Automation ← Screenshot/Results
     ↓
Text-to-Speech Response
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Redis server
- API keys for:
  - Deepgram
  - OpenAI
  - Browserbase
  - Mem0

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd voice-browser-agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

4. **Start Redis server**
   ```bash
   redis-server
   ```

5. **Run the agent**
   ```bash
   # CLI version
   python voice_browser_agent.py
   
   # Web interface
   python web_interface.py
   ```

## 📋 Configuration

Edit the `.env` file with your API credentials:

```env
# Deepgram API
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# Browserbase API
BROWSERBASE_API_KEY=your_browserbase_api_key_here
BROWSERBASE_PROJECT_ID=your_project_id_here

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Mem0 Configuration
MEM0_API_KEY=your_mem0_api_key_here
```

## 🎯 Usage Examples

### Basic Voice Commands

- "Go to Google"
- "Search for Python tutorials"
- "Click on the login button"
- "Type my email address"
- "Take a screenshot"
- "Extract all the product prices"

### Multi-step Workflows

- "Go to Amazon, search for wireless headphones, filter by price under $100, and add the first result to cart"
- "Navigate to GitHub, search for machine learning repositories, and download the first one"
- "Fill out the contact form with my name and email, then submit it"

### Data Extraction

- "Extract all the headlines from this news page"
- "Get all the product links and prices"
- "Extract the contact information from this page"

## 🛠️ API Endpoints

### Web Interface
- `GET /` - Main web interface
- `WebSocket /ws` - Real-time communication
- `POST /transcribe` - Audio transcription
- `POST /command` - Execute browser command
- `GET /stats` - Agent statistics
- `POST /screenshot` - Take screenshot
- `POST /reset` - Reset session

### CLI Commands
```bash
# Run demo
python demo.py

# Start web server
python web_interface.py

# Run agent directly
python voice_browser_agent.py
```

## 🔧 Components

### Voice Input (`voice_input.py`)
- Real-time audio capture
- Deepgram speech-to-text integration
- Audio file transcription

### Intent Parser (`intent_parser.py`)
- Natural language understanding
- Command structure conversion
- Multi-step workflow parsing

### Redis Cache (`redis_cache.py`)
- Conversation state management
- Browser state persistence
- Session data storage

### Browser Automation (`browser_automation.py`)
- Browserbase API integration
- Command execution
- Screenshot capture
- Data extraction

### Memory Layer (`memory_layer.py`)
- Mem0 integration
- Persistent knowledge storage
- Context retrieval

### Text-to-Speech (`text_to_speech.py`)
- Voice response generation
- Response formatting
- Audio output

## 📊 Supported Commands

| Command Type | Description | Example |
|--------------|-------------|---------|
| `NAVIGATE` | Navigate to URL | "Go to Google" |
| `SEARCH` | Search on page | "Search for Python tutorials" |
| `CLICK` | Click element | "Click the login button" |
| `TYPE` | Type text | "Type my email address" |
| `EXTRACT` | Extract data | "Extract all prices" |
| `SCROLL` | Scroll page | "Scroll down" |
| `WAIT` | Wait for condition | "Wait for page to load" |
| `SCREENSHOT` | Take screenshot | "Take a screenshot" |
| `FILTER` | Filter content | "Filter by price under $100" |
| `FILL_FORM` | Fill form | "Fill out contact form" |
| `DOWNLOAD` | Download file | "Download the PDF" |
| `UPLOAD` | Upload file | "Upload my resume" |

## 🎮 Demo Modes

1. **Basic Commands**: Test individual voice commands
2. **Workflow Demo**: Multi-step task automation
3. **Data Extraction**: Content extraction capabilities
4. **Interactive**: Real-time command testing

## 🔍 Troubleshooting

### Common Issues

1. **Microphone not working**
   - Check browser permissions
   - Ensure microphone is connected
   - Try refreshing the page

2. **API errors**
   - Verify API keys in `.env`
   - Check API quotas and limits
   - Ensure internet connection

3. **Browser automation fails**
   - Check Browserbase API key
   - Verify project ID
   - Check browser session status

4. **Redis connection issues**
   - Ensure Redis server is running
   - Check Redis URL configuration
   - Verify Redis password

### Debug Mode

Enable debug logging:
```python
# In config.py
DEBUG = True
LOG_LEVEL = "DEBUG"
```

## 🙏 Acknowledgments

- [Deepgram](https://deepgram.com/) for speech-to-text
- [OpenAI](https://openai.com/) for language understanding
- [Browserbase](https://browserbase.com/) for browser automation
- [Mem0](https://mem0.ai/) for memory management
- [Redis](https://redis.io/) for caching
- [FastAPI](https://fastapi.tiangolo.com/) for web framework


## System Design


<img width="740" height="266" alt="Screenshot 2025-09-20 at 9 41 17 PM" src="https://github.com/user-attachments/assets/6f5de3b5-3781-443b-877c-e73af2ead1d2" />
