"""
Configuration module for Voice-Enabled Browser Agent
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Keys
    deepgram_api_key: str
    openai_api_key: str
    anthropic_api_key: Optional[str] = None
    browserbase_api_key: str
    browserbase_project_id: str
    mem0_api_key: str
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    
    # Application Settings
    debug: bool = True
    log_level: str = "INFO"
    port: int = 8000
    host: str = "0.0.0.0"
    
    # Voice Settings
    voice_language: str = "en-US"
    voice_rate: int = 200
    voice_volume: float = 0.8
    
    # Browser Settings
    browser_headless: bool = True
    browser_timeout: int = 30000
    screenshot_quality: int = 90
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
