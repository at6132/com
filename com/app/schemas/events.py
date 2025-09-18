"""
Event-specific request and response schemas
Matches the JSON schema specification exactly
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from .base import WSEvent, ErrorEnvelope

# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class EventsListResponse(BaseModel):
    """Events List Response - matches JSON schema exactly"""
    events: List[WSEvent] = Field(description="List of events")
    next_cursor: Optional[str] = Field(default=None, description="Next cursor for pagination")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# WEB SOCKET MESSAGES
# ============================================================================

class WSMessage(BaseModel):
    """Base WebSocket message"""
    type: str = Field(description="Message type")
    
    model_config = ConfigDict(extra="forbid")

class WSAuthMessage(WSMessage):
    """WebSocket authentication message"""
    type: str = Field(default="AUTH", description="Message type")
    key_id: str = Field(description="API key ID")
    ts: int = Field(description="Timestamp")
    signature: str = Field(description="HMAC signature")
    
    model_config = ConfigDict(extra="forbid")

class WSSubscribeMessage(WSMessage):
    """WebSocket subscription message"""
    type: str = Field(default="SUBSCRIBE", description="Message type")
    strategy_id: str = Field(description="Strategy ID to subscribe to")
    
    model_config = ConfigDict(extra="forbid")

class WSUnsubscribeMessage(WSMessage):
    """WebSocket unsubscription message"""
    type: str = Field(default="UNSUBSCRIBE", description="Message type")
    strategy_id: str = Field(description="Strategy ID to unsubscribe from")
    
    model_config = ConfigDict(extra="forbid")

class WSPingMessage(WSMessage):
    """WebSocket ping message"""
    type: str = Field(default="PING", description="Message type")
    ts: int = Field(description="Timestamp")
    
    model_config = ConfigDict(extra="forbid")

class WSPongMessage(WSMessage):
    """WebSocket pong message"""
    type: str = Field(default="PONG", description="Message type")
    
    model_config = ConfigDict(extra="forbid")

class WSEventMessage(WSMessage):
    """WebSocket event message"""
    type: str = Field(default="EVENT", description="Message type")
    event: WSEvent = Field(description="Event data")
    
    model_config = ConfigDict(extra="forbid")

class WSErrorMessage(WSMessage):
    """WebSocket error message"""
    type: str = Field(default="ERROR", description="Message type")
    error: str = Field(description="Error message")
    code: Optional[str] = Field(default=None, description="Error code")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# WEB SOCKET RESPONSES
# ============================================================================

class WSAuthResponse(BaseModel):
    """WebSocket authentication response"""
    status: str = Field(description="Authentication status: AUTH_ACK or AUTH_NACK")
    message: Optional[str] = Field(default=None, description="Status message")
    
    model_config = ConfigDict(extra="forbid")

class WSSubscribeResponse(BaseModel):
    """WebSocket subscription response"""
    status: str = Field(description="Subscription status: SUBSCRIBED or UNSUBSCRIBED")
    strategy_id: str = Field(description="Strategy ID")
    message: Optional[str] = Field(default=None, description="Status message")
    
    model_config = ConfigDict(extra="forbid")

class WSPongResponse(BaseModel):
    """WebSocket pong response"""
    ts: int = Field(description="Timestamp")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# INTERNAL MODELS
# ============================================================================

class EventQuery(BaseModel):
    """Event query parameters"""
    since: Optional[datetime] = Field(default=None, description="Events since this time")
    strategy_id: Optional[str] = Field(default=None, description="Filter by strategy")
    limit: Optional[int] = Field(default=100, ge=1, le=1000, description="Maximum events to return")
    cursor: Optional[str] = Field(default=None, description="Pagination cursor")
    
    model_config = ConfigDict(extra="forbid")

class EventReplayResult(BaseModel):
    """Internal event replay result"""
    success: bool
    events: List[WSEvent] = Field(default_factory=list, description="Replayed events")
    next_cursor: Optional[str] = Field(default=None, description="Next cursor")
    error: Optional[str] = Field(default=None, description="Error message")
    
    model_config = ConfigDict(extra="forbid")

class EventBroadcastResult(BaseModel):
    """Internal event broadcast result"""
    success: bool
    subscribers_notified: int = Field(description="Number of subscribers notified")
    error: Optional[str] = Field(default=None, description="Error message")
    
    model_config = ConfigDict(extra="forbid")
