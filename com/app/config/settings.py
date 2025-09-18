"""
Configuration management for COM backend
Environment separation and settings management
"""
import os
from typing import Optional, Dict, Any, List
from functools import lru_cache

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    # Try Pydantic v2 first
    from pydantic_settings import BaseSettings
    from pydantic import Field, validator
except ImportError:
    # Fallback to Pydantic v1
    from pydantic import BaseSettings, Field, validator

class Settings(BaseSettings):
    """Main application settings"""
    
    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(False, env="DEBUG")
    
    # Server
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    workers: int = Field(1, env="WORKERS")
    
    # Database settings
    database_url: str = Field(..., env="DATABASE_URL")
    db_echo: bool = Field(False, env="DB_ECHO")
    db_pool_size: int = Field(5, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(10, env="DB_MAX_OVERFLOW")
    
    # Redis settings
    redis_url: str = Field(..., env="REDIS_URL")
    redis_db: int = Field(0, env="REDIS_DB")
    redis_password: Optional[str] = Field(None, env="REDIS_PASSWORD")
    
    # MEXC settings
    mexc_api_key: str = Field(..., env="MEXC_API_KEY")
    mexc_secret_key: str = Field(..., env="MEXC_SECRET_KEY")
    mexc_sandbox: bool = Field(True, env="MEXC_SANDBOX")
    mexc_base_url: str = Field("https://www.mexc.com", env="MEXC_BASE_URL")
    mexc_testnet_url: str = Field("https://testnet.mexc.com", env="MEXC_TESTNET_URL")
    
    # Security settings
    security_secret_key: str = Field(..., env="SECURITY_SECRET_KEY")
    api_key_salt: str = Field(..., env="API_KEY_SALT")
    security_algorithm: str = Field("HS256", env="SECURITY_ALGORITHM")
    security_access_token_expire_minutes: int = Field(30, env="SECURITY_ACCESS_TOKEN_EXPIRE_MINUTES")
    security_hmac_clock_skew_seconds: int = Field(300, env="SECURITY_HMAC_CLOCK_SKEW_SECONDS")
    
    # Risk settings
    risk_max_order_size_usd: float = Field(100000.0, env="RISK_MAX_ORDER_SIZE_USD")
    risk_max_daily_volume_usd: float = Field(1000000.0, env="RISK_MAX_DAILY_VOLUME_USD")
    risk_max_position_size_usd: float = Field(500000.0, env="RISK_MAX_POSITION_SIZE_USD")
    risk_max_requests_per_minute: int = Field(1000, env="RISK_MAX_REQUESTS_PER_MINUTE")
    
    # Logging settings
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_format: str = Field("%(asctime)s - %(name)s - %(levelname)s - %(message)s", env="LOG_FORMAT")
    log_json_format: bool = Field(True, env="LOG_JSON_FORMAT")
    
    # Feature flags
    enable_websockets: bool = Field(True, env="ENABLE_WEBSOCKETS")
    enable_exit_engine: bool = Field(True, env="ENABLE_EXIT_ENGINE")
    enable_balance_polling: bool = Field(True, env="ENABLE_BALANCE_POLLING")
    
    # CORS settings
    cors_origins: List[str] = Field(default=["*"], env="CORS_ORIGINS")
    
    @validator('environment')
    def validate_environment(cls, v):
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'Environment must be one of: {allowed}')
        return v
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
