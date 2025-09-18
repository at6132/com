"""
HMAC authentication system for COM backend
Implements secure authentication for REST and WebSocket endpoints
"""
import hashlib
import hmac
import time
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt

from ..core.database import get_db, ApiKey
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# Maximum timestamp skew (5 minutes)
MAX_TIMESTAMP_SKEW = 300  # seconds

# Rate limiting
RATE_LIMIT_PER_MINUTE = 1000
RATE_LIMIT_PER_HOUR = 10000

# ============================================================================
# HMAC AUTHENTICATION
# ============================================================================

class HMACAuth:
    """HMAC authentication handler"""
    
    @staticmethod
    def verify_signature(
        key_id: str,
        signature: str,
        timestamp: int,
        method: str,
        path: str,
        body: str,
        secret: str
    ) -> bool:
        """Verify HMAC signature"""
        try:
            # Create signature base string
            base_string = f"{timestamp}\n{method}\n{path}\n{body}"
            
            # Generate expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                base_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (constant-time comparison)
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    @staticmethod
    def verify_timestamp(timestamp: int) -> bool:
        """Verify timestamp is within acceptable range"""
        current_time = int(time.time())
        return abs(current_time - timestamp) <= MAX_TIMESTAMP_SKEW

# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def verify_hmac_signature(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> bool:
    """Verify HMAC signature for request"""
    try:
        # Get request details
        method = request.method
        path = request.url.path
        
        # Get request body
        body = ""
        if request.body:
            body = await request.body()
            body = body.decode('utf-8')
        
        # Get HMAC parameters from header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("HMAC "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header"
            )
        
        # Parse HMAC parameters
        parts = auth_header[5:].split(",")
        signature = None
        timestamp = None
        key_id = None
        
        for part in parts:
            part = part.strip()
            if part.startswith("signature="):
                signature = part[11:].strip('"')
            elif part.startswith("ts="):
                timestamp_str = part[3:].strip()  # Remove 'ts=' and any whitespace
                timestamp = int(timestamp_str)
            elif part.startswith("key_id="):
                key_id = part[8:].strip('"')
        
        if not signature or not timestamp or not key_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature, timestamp, or key_id"
            )
        
        # Get API key from database
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_id == key_id,
                ApiKey.is_active == True
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Verify signature
        logger.info(f"Verifying HMAC signature:")
        logger.info(f"  Key ID: {api_key.key_id}")
        logger.info(f"  Method: {method}")
        logger.info(f"  Path: {path}")
        logger.info(f"  Body: {body[:100]}...")
        logger.info(f"  Timestamp: {timestamp}")
        logger.info(f"  Received signature: {signature}")
        logger.info(f"  Secret key length: {len(api_key.secret_key)}")
        
        if not HMACAuth.verify_signature(
            api_key.key_id,
            signature,
            timestamp,
            method,
            path,
            body,
            api_key.secret_key  # Use actual secret key, not hash
        ):
            logger.error("HMAC signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        logger.info("HMAC signature verification successful")
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying HMAC signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signature verification error"
        )

# ============================================================================
# WEBSOCKET HMAC AUTHENTICATION
# ============================================================================

def verify_websocket_hmac_signature(
    secret_key: str,
    signature: str,
    timestamp: int,
    auth_data: Dict[str, Any]
) -> bool:
    """Verify HMAC signature for WebSocket authentication"""
    try:
        # Create the data string to sign: key_id + newline + timestamp
        key_id = auth_data.get("key_id", "")
        data_string = f"{key_id}\n{timestamp}"
        
        # Generate expected signature
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (constant-time comparison)
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        logger.info(f"WebSocket HMAC verification:")
        logger.info(f"  Key ID: {key_id}")
        logger.info(f"  Timestamp: {timestamp}")
        logger.info(f"  Data string: {data_string}")
        logger.info(f"  Received signature: {signature}")
        logger.info(f"  Expected signature: {expected_signature}")
        logger.info(f"  Valid: {is_valid}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Error verifying WebSocket HMAC signature: {e}")
        return False

# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """Rate limiting implementation"""
    
    def __init__(self):
        self.requests_per_minute = {}
        self.requests_per_hour = {}
    
    def is_allowed(self, key_id: str, limit_type: str = "minute") -> bool:
        """Check if request is allowed"""
        current_time = time.time()
        
        if limit_type == "minute":
            window = 60
            limit = RATE_LIMIT_PER_MINUTE
            requests = self.requests_per_minute
        else:  # hour
            window = 3600
            limit = RATE_LIMIT_PER_HOUR
            requests = self.requests_per_hour
        
        # Clean old entries
        cutoff = current_time - window
        if key_id in requests:
            requests[key_id] = [t for t in requests[key_id] if t > cutoff]
        else:
            requests[key_id] = []
        
        # Check limit
        if len(requests[key_id]) >= limit:
            return False
        
        # Add current request
        requests[key_id].append(current_time)
        return True

# Global rate limiter instance
rate_limiter = RateLimiter()

async def check_rate_limit(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> bool:
    """Check rate limits for API key"""
    # Parse key_id from Authorization header
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("HMAC "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )
    
    # Extract key_id
    parts = auth_header[5:].split(",")
    key_id = None
    for part in parts:
        part = part.strip()
        if part.startswith("key_id="):
            key_id = part[8:].strip('"')
            break
    
    if not key_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing key_id in authorization header"
        )
    
    # Check rate limits
    if not rate_limiter.is_allowed(key_id, "minute"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded (per minute)"
        )
    
    if not rate_limiter.is_allowed(key_id, "hour"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded (per hour)"
        )
    
    return True

# ============================================================================
# WEB SOCKET AUTHENTICATION
# ============================================================================

async def verify_ws_auth(
    key_id: str,
    signature: str,
    timestamp: int,
    db: AsyncSession
) -> Optional[ApiKey]:
    """Verify WebSocket authentication"""
    try:
        # Verify timestamp
        if not HMACAuth.verify_timestamp(timestamp):
            return None
        
        # Get API key from database
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_id == key_id,
                ApiKey.is_active == True
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            return None
        
        # Check if key is expired
        if api_key.expires_at and api_key.expires_at.timestamp() < time.time():
            return None
        
        # Update last used timestamp
        api_key.last_used_at = time.time()
        await db.commit()
        
        return api_key
        
    except Exception as e:
        logger.error(f"Error verifying WebSocket auth: {e}")
        return None

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def hash_secret(secret: str) -> str:
    """Hash API key secret using bcrypt"""
    return bcrypt.hashpw(secret.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_secret(secret: str, hashed: str) -> bool:
    """Verify API key secret against hash"""
    return bcrypt.checkpw(secret.encode('utf-8'), hashed.encode('utf-8'))

def create_hmac_header(
    key_id: str,
    secret: str,
    method: str,
    path: str,
    body: str = ""
) -> str:
    """Create HMAC authorization header for testing"""
    timestamp = int(time.time())
    base_string = f"{timestamp}\n{method}\n{path}\n{body}"
    
    signature = hmac.new(
        secret.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return f"HMAC key_id=\"{key_id}\", signature=\"{signature}\", ts={timestamp}"
