#!/usr/bin/env python3
"""
Test script to verify Voice-Enabled Browser Agent installation
"""
import sys
import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_imports():
    """Test if all required packages can be imported"""
    print("🧪 Testing package imports...")
    
    required_packages = [
        ("deepgram", "Deepgram SDK"),
        ("openai", "OpenAI SDK"),
        ("redis", "Redis client"),
        ("mem0", "Mem0 SDK"),
        ("pyttsx3", "Text-to-speech"),
        ("pyaudio", "Audio processing"),
        ("fastapi", "FastAPI web framework"),
        ("uvicorn", "ASGI server"),
        ("aiohttp", "Async HTTP client"),
        ("PIL", "Pillow image processing"),
        ("pydantic", "Data validation"),
        ("asyncio", "Async support")
    ]
    
    failed_imports = []
    
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"✅ {name}")
        except ImportError as e:
            print(f"❌ {name}: {e}")
            failed_imports.append(name)
    
    if failed_imports:
        print(f"\n❌ Failed to import: {', '.join(failed_imports)}")
        return False
    
    print("✅ All packages imported successfully")
    return True


def test_config():
    """Test configuration file"""
    print("\n⚙️  Testing configuration...")
    
    config_file = Path("config.py")
    env_file = Path(".env")
    
    if not config_file.exists():
        print("❌ config.py not found")
        return False
    
    if not env_file.exists():
        print("❌ .env file not found")
        return False
    
    print("✅ Configuration files found")
    
    # Test config import
    try:
        from config import settings
        print("✅ Configuration loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False


def test_redis_connection():
    """Test Redis connection"""
    print("\n🔍 Testing Redis connection...")
    
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Make sure Redis server is running: redis-server")
        return False


async def test_agent_components():
    """Test individual agent components"""
    print("\n🤖 Testing agent components...")
    
    try:
        # Test voice input
        from voice_input import VoiceInputHandler
        voice_handler = VoiceInputHandler()
        print("✅ Voice input handler created")
        
        # Test intent parser
        from intent_parser import IntentParser
        intent_parser = IntentParser()
        print("✅ Intent parser created")
        
        # Test Redis cache
        from redis_cache import RedisCache
        redis_cache = RedisCache()
        redis_cache.set_session_id("test_session")
        print("✅ Redis cache created")
        
        # Test browser automation
        from browser_automation import BrowserAutomation
        browser_automation = BrowserAutomation()
        print("✅ Browser automation created")
        
        # Test memory layer
        from memory_layer import MemoryLayer
        memory_layer = MemoryLayer()
        memory_layer.set_session_id("test_session")
        print("✅ Memory layer created")
        
        # Test TTS
        from text_to_speech import TextToSpeech
        tts = TextToSpeech()
        print("✅ Text-to-speech created")
        
        # Cleanup
        tts.cleanup()
        print("✅ Component cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Component test failed: {e}")
        return False


async def test_agent_initialization():
    """Test full agent initialization"""
    print("\n🚀 Testing agent initialization...")
    
    try:
        from voice_browser_agent import VoiceBrowserAgent
        
        agent = VoiceBrowserAgent()
        print("✅ Agent instance created")
        
        # Test initialization (without actually starting services)
        print("✅ Agent initialization test passed")
        
        return True
        
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        return False


def test_web_interface():
    """Test web interface"""
    print("\n🌐 Testing web interface...")
    
    try:
        from web_interface import app
        print("✅ FastAPI app created")
        
        # Test route registration
        routes = [route.path for route in app.routes]
        expected_routes = ["/", "/ws", "/transcribe", "/command", "/stats", "/screenshot", "/reset"]
        
        for route in expected_routes:
            if route in routes:
                print(f"✅ Route {route} registered")
            else:
                print(f"❌ Route {route} missing")
                return False
        
        print("✅ Web interface test passed")
        return True
        
    except Exception as e:
        print(f"❌ Web interface test failed: {e}")
        return False


async def main():
    """Main test function"""
    print("🧪 Voice-Enabled Browser Agent - Installation Test")
    print("=" * 60)
    
    tests = [
        ("Package Imports", test_imports),
        ("Configuration", test_config),
        ("Redis Connection", test_redis_connection),
        ("Agent Components", test_agent_components),
        ("Agent Initialization", test_agent_initialization),
        ("Web Interface", test_web_interface)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print(f"\n{'='*60}")
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Installation is successful.")
        print("\n🚀 You can now run the agent:")
        print("   - CLI: python voice_browser_agent.py")
        print("   - Web: python web_interface.py")
        print("   - Demo: python demo.py")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\n🔧 Common fixes:")
        print("   - Install missing packages: pip install -r requirements.txt")
        print("   - Start Redis server: redis-server")
        print("   - Configure API keys in .env file")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
