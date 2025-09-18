"""
Order-specific request and response schemas
Matches the JSON schema specification exactly
"""
from typing import Dict, Any, Union, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from .base import (
    OrderRequest, AmendOrderRequest, OrderView, 
    Ack, ErrorEnvelope, Environment, Source
)

# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class CreateOrderRequest(BaseModel):
    """Create Order Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    source: Source = Field(description="Source information")
    order: OrderRequest = Field(description="Order details")
    
    model_config = ConfigDict(extra="forbid")

class AmendOrderRequestWrapper(BaseModel):
    """Amend Order Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    changes: Dict[str, Any] = Field(description="Changes to apply", min_properties=1)
    
    model_config = ConfigDict(extra="forbid")

class CancelOrderRequest(BaseModel):
    """Cancel Order Request - matches JSON schema exactly"""
    idempotency_key: str = Field(min_length=8, max_length=200, description="Idempotency key")
    environment: Environment = Field(description="Environment configuration")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class CreateOrderResponse(BaseModel):
    """Create Order Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    # This will be handled by FastAPI response_model with Union[Ack, ErrorEnvelope]
    pass

class AmendOrderResponse(BaseModel):
    """Amend Order Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class CancelOrderResponse(BaseModel):
    """Cancel Order Response - matches JSON schema exactly"""
    # OneOf: Ack or ErrorEnvelope
    pass

class GetOrderResponse(BaseModel):
    """Get Order Response - matches JSON schema exactly"""
    # OneOf: OrderView or ErrorEnvelope
    pass

# ============================================================================
# INTERNAL MODELS
# ============================================================================

class OrderCreateResult(BaseModel):
    """Internal order creation result"""
    success: bool
    order_ref: Optional[str] = None
    position_ref: Optional[str] = None
    broker_order_id: Optional[str] = None
    adjustments: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class OrderAmendResult(BaseModel):
    """Internal order amendment result"""
    success: bool
    order_ref: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class OrderCancelResult(BaseModel):
    """Internal order cancellation result"""
    success: bool
    order_ref: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")
