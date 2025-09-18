"""
Idempotency system for COM backend
Prevents duplicate operations and enables safe retries
"""
import hashlib
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ..core.database import IdempotencyRecord
from ..schemas.base import ErrorEnvelope

logger = logging.getLogger(__name__)

# ============================================================================
# IDEMPOTENCY CONFIGURATION
# ============================================================================

# TTL for idempotency records (24 hours)
IDEMPOTENCY_TTL_HOURS = 24

# ============================================================================
# IDEMPOTENCY SERVICE
# ============================================================================

class IdempotencyService:
    """Idempotency management service"""
    
    def __init__(self):
        self.logger = logger
    
    async def check_idempotency(
        self,
        db: AsyncSession,
        idempotency_key: str,
        request_type: str,
        payload: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Check if idempotency key exists and return result
        
        Returns:
            Tuple of (exists, result_data, result_ref)
        """
        try:
            # Generate payload hash
            payload_hash = self._hash_payload(payload)
            
            # Check for existing record
            result = await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key == idempotency_key
                )
            )
            record = result.scalar_one_or_none()
            
            if not record:
                return False, None, None
            
            # Check if record is expired
            if record.expires_at < datetime.utcnow():
                # Clean up expired record
                await db.delete(record)
                await db.commit()
                return False, None, None
            
            # Check if request type matches
            if record.request_type != request_type:
                # Different request type - this is a duplicate intent
                return True, None, record.result_ref
            
            # Check if payload hash matches
            if record.payload_hash == payload_hash:
                # Same payload - return stored result
                # Parse JSON string back to dictionary
                result_data = json.loads(record.result_data) if record.result_data else None
                return True, result_data, record.result_ref
            else:
                # Different payload - duplicate intent
                return True, None, record.result_ref
                
        except Exception as e:
            self.logger.error(f"Error checking idempotency: {e}")
            # On error, allow the request to proceed
            return False, None, None
    
    async def store_idempotency(
        self,
        db: AsyncSession,
        idempotency_key: str,
        request_type: str,
        payload: Dict[str, Any],
        result_ref: str,
        result_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store idempotency record"""
        try:
            # Generate payload hash
            payload_hash = self._hash_payload(payload)
            
            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
            
            # Create or update record
            # Convert result_data to JSON string for SQLite compatibility
            result_data_json = json.dumps(result_data) if result_data else None
            
            record = IdempotencyRecord(
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                request_type=request_type,
                result_ref=result_ref,
                result_data=result_data_json,
                expires_at=expires_at
            )
            
            db.add(record)
            await db.commit()
            
            self.logger.info(f"Stored idempotency record for key: {idempotency_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing idempotency record: {e}")
            await db.rollback()
            return False
    
    async def cleanup_expired_records(self, db: AsyncSession) -> int:
        """Clean up expired idempotency records"""
        try:
            result = await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.expires_at < datetime.utcnow()
                )
            )
            expired_records = result.scalars().all()
            
            count = len(expired_records)
            for record in expired_records:
                await db.delete(record)
            
            await db.commit()
            
            if count > 0:
                self.logger.info(f"Cleaned up {count} expired idempotency records")
            
            return count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up expired records: {e}")
            await db.rollback()
            return 0
    
    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        """Generate SHA256 hash of payload"""
        # Sort keys to ensure consistent hashing
        sorted_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(sorted_payload.encode('utf-8')).hexdigest()

# Global idempotency service instance
idempotency_service = IdempotencyService()

# ============================================================================
# IDEMPOTENCY MIDDLEWARE
# ============================================================================

async def check_idempotency_middleware(
    request_type: str,
    idempotency_key: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Middleware function to check idempotency"""
    return await idempotency_service.check_idempotency(
        db, idempotency_key, request_type, payload
    )

async def store_idempotency_middleware(
    request_type: str,
    idempotency_key: str,
    payload: Dict[str, Any],
    result_ref: str,
    result_data: Optional[Dict[str, Any]] = None,
    db: AsyncSession = None
) -> bool:
    """Middleware function to store idempotency record"""
    if db is None:
        # If no DB session provided, this is a no-op
        return True
    
    return await idempotency_service.store_idempotency(
        db, request_type, idempotency_key, payload, result_ref, result_data
    )

# ============================================================================
# ERROR HANDLING
# ============================================================================

def create_duplicate_intent_error(
    idempotency_key: str,
    existing_result_ref: str
) -> ErrorEnvelope:
    """Create duplicate intent error response"""
    return ErrorEnvelope(
        error={
            "code": "DUPLICATE_INTENT",
            "message": "Idempotency key exists with different payload",
            "idempotency_key": idempotency_key,
            "details": {
                "existing_result_ref": existing_result_ref,
                "error_type": "duplicate_intent"
            }
        }
    )

def create_duplicate_idempotency_error(
    idempotency_key: str,
    existing_result_ref: str
) -> ErrorEnvelope:
    """Create duplicate idempotency key error response"""
    return ErrorEnvelope(
        error={
            "code": "DUPLICATE_IDEMPOTENCY_KEY",
            "message": "Idempotency key already exists",
            "idempotency_key": idempotency_key,
            "details": {
                "existing_result_ref": existing_result_ref,
            }
        }
    )

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_valid_idempotency_key(key: str) -> bool:
    """Validate idempotency key format"""
    if not key:
        return False
    
    # Check length (8-200 characters)
    if len(key) < 8 or len(key) > 200:
        return False
    
    # Check for valid characters (alphanumeric, hyphens, underscores)
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', key):
        return False
    
    return True

def generate_idempotency_key(prefix: str = "req") -> str:
    """Generate a unique idempotency key"""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
