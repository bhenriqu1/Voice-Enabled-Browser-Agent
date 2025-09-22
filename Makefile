# Voice-Enabled Browser Agent Makefile

.PHONY: help install setup test run-web run-cli run-demo clean

# Default target
help:
	@echo "🎤 Voice-Enabled Browser Agent"
	@echo "=============================="
	@echo ""
	@echo "Available commands:"
	@echo "  install    - Install Python dependencies"
	@echo "  setup      - Run complete setup (install + configure)"
	@echo "  test       - Run installation tests"
	@echo "  run-web    - Start web interface"
	@echo "  run-cli    - Start CLI version"
	@echo "  run-demo   - Run demo script"
	@echo "  clean      - Clean up temporary files"
	@echo ""

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt

# Run complete setup
setup:
	@echo "🚀 Running complete setup..."
	python setup.py

# Run tests
test:
	@echo "🧪 Running tests..."
	python test_installation.py

# Start web interface
run-web:
	@echo "🌐 Starting web interface..."
	python web_interface.py

# Start CLI version
run-cli:
	@echo "💻 Starting CLI version..."
	python voice_browser_agent.py

# Run demo
run-demo:
	@echo "🎮 Running demo..."
	python demo.py

# Clean up
clean:
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type f -name "*.log" -delete
	rm -rf logs/
	rm -rf screenshots/
	rm -rf audio/
	rm -rf data/

# Development commands
dev-install:
	@echo "🔧 Installing development dependencies..."
	pip install -r requirements.txt
	pip install black flake8 pytest

format:
	@echo "🎨 Formatting code..."
	black *.py

lint:
	@echo "🔍 Linting code..."
	flake8 *.py

# Redis commands
redis-start:
	@echo "🔴 Starting Redis server..."
	redis-server

redis-stop:
	@echo "🔴 Stopping Redis server..."
	redis-cli shutdown

redis-status:
	@echo "🔍 Checking Redis status..."
	redis-cli ping

# Quick start
quick-start: setup test run-web
	@echo "🚀 Quick start completed!"

# Full test suite
test-all: test run-demo
	@echo "✅ All tests completed!"
