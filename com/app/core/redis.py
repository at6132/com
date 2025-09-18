"""
Redis configuration and initialization
Caching and pub/sub support
"""
import logging
from typing import Optional

import redis.asyncio as redis
from ..config import get_settings

logger = logging.getLogger(__name__)

# Global Redis client
redis_client: Optional[redis.Redis] = None

async def init_redis() -> None:
    """Initialize Redis connection"""
    global redis_client
    
    try:
        # Get current settings
        settings = get_settings()
        
        # Parse Redis URL
        redis_url = settings.redis_url
        
        # Create Redis client
        redis_client = redis.from_url(
            redis_url,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            retry_on_timeout=True,
            health_check_interval=30,
        )
        
        # Test connection
        await redis_client.ping()
        
        logger.info("Redis initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise

async def close_redis() -> None:
    """Close Redis connections"""
    global redis_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connections closed")

async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    if not redis_client:
        raise RuntimeError("Redis not initialized")
    return redis_client

async def health_check_redis() -> bool:
    """Check Redis health"""
    try:
        if redis_client:
            await redis_client.ping()
            return True
        return False
    except Exception:
        return False
