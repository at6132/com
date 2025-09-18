"""
Position-specific request and response schemas
Matches the JSON schema specification exactly
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from .base import (
    ExitLeg, PositionView, SubOrderView, 
    Ack, ErrorEnvelope, Environment
)

# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class CreateSubOrderRequest(BaseModel):
    """Create Suborder Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    leg: ExitLeg = Field(description="Exit plan leg")
    
    model_config = ConfigDict(extra="forbid")

class AmendSubOrderRequest(BaseModel):
    """Amend Suborder Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    changes: Dict[str, Any] = Field(description="Changes to apply", min_properties=1)
    
    model_config = ConfigDict(extra="forbid")

class CancelSubOrderRequest(BaseModel):
    """Cancel Suborder Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    
    model_config = ConfigDict(extra="forbid")

class ClosePositionRequest(BaseModel):
    """Close Position Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    amount: Dict[str, Any] = Field(description="Close amount specification")
    order: Dict[str, Any] = Field(description="Close order specification")
    guards: Optional[Dict[str, Any]] = Field(default=None, description="Risk guards")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class CreateSubOrderResponse(BaseModel):
    """Create Suborder Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class AmendSubOrderResponse(BaseModel):
    """Amend Suborder Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class CancelSubOrderResponse(BaseModel):
    """Cancel Suborder Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class ClosePositionResponse(BaseModel):
    """Close Position Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class GetPositionResponse(BaseModel):
    """Get Position Response - matches JSON schema exactly"""
    # OneOf: PositionView or ErrorEnvelope
    pass

class ListPositionsResponse(BaseModel):
    """List Positions Response - matches JSON schema exactly"""
    positions: List[PositionView] = Field(description="List of positions")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# INTERNAL MODELS
# ============================================================================

class SubOrderCreateResult(BaseModel):
    """Internal suborder creation result"""
    success: bool
    sub_order_ref: Optional[str] = None
    position_ref: Optional[str] = None
    broker_order_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class SubOrderAmendResult(BaseModel):
    """Internal suborder amendment result"""
    success: bool
    sub_order_ref: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class SubOrderCancelResult(BaseModel):
    """Internal suborder cancellation result"""
    success: bool
    sub_order_ref: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class PositionCloseResult(BaseModel):
    """Internal position close result"""
    success: bool
    position_ref: Optional[str] = None
    order_ref: Optional[str] = None
    broker_order_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class PositionQuery(BaseModel):
    """Position query parameters"""
    symbol: Optional[str] = Field(default=None, description="Filter by symbol")
    strategy_id: Optional[str] = Field(default=None, description="Filter by strategy")
    
    model_config = ConfigDict(extra="forbid")
