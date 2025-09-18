"""
Order API endpoints for COM backend
Implements the order management REST API
"""
from typing import Union
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.orders import (
    CreateOrderRequest, AmendOrderRequestWrapper, CancelOrderRequest,
    Ack, ErrorEnvelope, OrderView
)
from ...services.orders import order_service
from ...services.order_monitor import order_monitor
from ...core.database import get_db
from ...security.auth import verify_hmac_signature, check_rate_limit

router = APIRouter()

# ============================================================================
# ORDER ENDPOINTS
# ============================================================================

@router.post("/orders", response_model=None)
async def create_order(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_hmac_signature),
    __: bool = Depends(check_rate_limit)
) -> Union[Ack, ErrorEnvelope]:
    """Create a new order"""
    try:
        result, ack, error = await order_service.create_order(request, db)
        
        if result.success and ack:
            return ack
        elif error:
            return error
        else:
            # This shouldn't happen, but handle gracefully
            raise HTTPException(status_code=500, detail="Unexpected response from order service")
            
    except Exception as e:
        # Log the error and return internal error
        error = ErrorEnvelope(
            error={
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}",
                "idempotency_key": request.idempotency_key
            }
        )
        return error

@router.post("/orders/{order_ref}/amend", response_model=None)
async def amend_order(
    order_ref: str, 
    request: AmendOrderRequestWrapper,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_hmac_signature),
    __: bool = Depends(check_rate_limit)
) -> Union[Ack, ErrorEnvelope]:
    """Amend an existing order"""
    try:
        result, ack, error = await order_service.amend_order(order_ref, request, db)
        
        if result.success and ack:
            return ack
        elif error:
            return error
        else:
            raise HTTPException(status_code=500, detail="Unexpected response from order service")
            
    except Exception as e:
        error = ErrorEnvelope(
            error={
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}",
                "idempotency_key": request.idempotency_key
            }
        )
        return error

@router.post("/orders/{order_ref}/cancel", response_model=None)
async def cancel_order(
    order_ref: str, 
    request: CancelOrderRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_hmac_signature),
    __: bool = Depends(check_rate_limit)
) -> Union[Ack, ErrorEnvelope]:
    """Cancel an existing order"""
    try:
        result, ack, error = await order_service.cancel_order(order_ref, request, db)
        
        if result.success and ack:
            return ack
        elif error:
            return error
        else:
            raise HTTPException(status_code=500, detail="Unexpected response from order service")
            
    except Exception as e:
        error = ErrorEnvelope(
            error={
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}",
                "idempotency_key": request.idempotency_key
            }
        )
        return error

@router.get("/orders/{order_ref}", response_model=None)
async def get_order(
    order_ref: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_hmac_signature)
) -> Union[OrderView, ErrorEnvelope]:
    """Get order details"""
    try:
        order = await order_service.get_order(order_ref, db)
        
        if order:
            return order
        else:
            error = ErrorEnvelope(
                error={
                    "code": "POSITION_NOT_FOUND",
                    "message": f"Order {order_ref} not found",
                    "details": {"order_ref": order_ref}
                }
            )
            return error
            
    except Exception as e:
        error = ErrorEnvelope(
            error={
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}"
            }
        )
        return error

@router.get("/monitoring/status")
async def get_monitoring_status():
    """Get order monitoring service status"""
    try:
        stats = order_monitor.get_monitoring_stats()
        return JSONResponse(content={
            "status": "success",
            "data": stats
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get monitoring status: {str(e)}"
            }
        )
