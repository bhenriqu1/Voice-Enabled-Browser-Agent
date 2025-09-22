#!/usr/bin/env python3
"""
Setup script for Voice-Enabled Browser Agent
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False


def check_python_version():
    """Check if Python version is compatible"""
    print("🐍 Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {sys.version.split()[0]} is compatible")
    return True


def check_redis():
    """Check if Redis is available"""
    print("🔍 Checking Redis availability...")
    try:
        result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True)
        if "PONG" in result.stdout:
            print("✅ Redis is running")
            return True
        else:
            print("⚠️  Redis is not running. Please start Redis server:")
            print("   redis-server")
            return False
    except FileNotFoundError:
        print("❌ Redis is not installed. Please install Redis:")
        print("   macOS: brew install redis")
        print("   Ubuntu: sudo apt-get install redis-server")
        print("   Windows: Download from https://redis.io/download")
        return False


def install_dependencies():
    """Install Python dependencies"""
    print("📦 Installing Python dependencies...")
    return run_command("pip install -r requirements.txt", "Installing dependencies")


def create_env_file():
    """Create .env file from template"""
    print("⚙️  Setting up environment configuration...")
    
    env_file = Path(".env")
    env_example = Path("env.example")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print("✅ Created .env file from template")
        print("⚠️  Please edit .env file with your API keys")
        return True
    else:
        print("❌ env.example file not found")
        return False


def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    directories = ["logs", "screenshots", "audio", "data"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created directory: {directory}")
    
    return True


def check_api_keys():
    """Check if API keys are configured"""
    print("🔑 Checking API key configuration...")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found")
        return False
    
    required_keys = [
        "DEEPGRAM_API_KEY",
        "OPENAI_API_KEY", 
        "BROWSERBASE_API_KEY",
        "BROWSERBASE_PROJECT_ID",
        "MEM0_API_KEY"
    ]
    
    missing_keys = []
    with open(env_file, 'r') as f:
        content = f.read()
        for key in required_keys:
            if f"{key}=your_" in content or f"{key}=" not in content:
                missing_keys.append(key)
    
    if missing_keys:
        print("⚠️  Missing or incomplete API keys:")
        for key in missing_keys:
            print(f"   - {key}")
        print("Please edit .env file with your actual API keys")
        return False
    
    print("✅ All API keys are configured")
    return True


def run_tests():
    """Run basic tests"""
    print("🧪 Running basic tests...")
    
    # Test imports
    try:
        import deepgram
        import openai
        import redis
        import mem0
        import pyttsx3
        print("✅ All required packages imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test Redis connection
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False
    
    print("✅ Basic tests passed")
    return True


def main():
    """Main setup function"""
    print("🚀 Voice-Enabled Browser Agent Setup")
    print("=" * 50)
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    if not check_redis():
        print("⚠️  Continuing setup, but Redis needs to be started before running the agent")
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Create configuration
    if not create_env_file():
        print("❌ Failed to create configuration file")
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Check API keys
    api_keys_ok = check_api_keys()
    
    # Run tests
    if not run_tests():
        print("❌ Tests failed")
        sys.exit(1)
    
    print("\n🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your API keys")
    print("2. Start Redis server: redis-server")
    print("3. Run the agent:")
    print("   - CLI: python voice_browser_agent.py")
    print("   - Web: python web_interface.py")
    print("   - Demo: python demo.py")
    
    if not api_keys_ok:
        print("\n⚠️  Remember to configure your API keys before running the agent!")
    
    print("\n📚 For more information, see README.md")


if __name__ == "__main__":
    main()
