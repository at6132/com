"""
Positions API endpoints
Position management and suborder operations
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from ...core.database import get_db
from ...schemas.positions import (
    CreateSubOrderRequest, AmendSubOrderRequest, CancelSubOrderRequest,
    ClosePositionRequest, SetTimeStopRequest, CancelTimeStopRequest,
    PositionView, ListPositionsResponse, SubOrderView
)
from ...schemas.base import Ack

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/{position_ref}/suborders", response_model=Ack)
async def create_suborder(
    position_ref: str,
    request: CreateSubOrderRequest,
    db: AsyncSession = Depends(get_db)
) -> Ack:
    """Create TP/SL leg (suborder) under a position"""
    try:
        # TODO: Implement suborder creation logic
        return Ack(
            status="ACK",
            received_at="2024-01-15T10:30:00Z",  # TODO: Use actual timestamp
            position_ref=position_ref,
            sub_order_ref="SUB_placeholder"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{position_ref}/suborders/{sub_order_ref}/amend", response_model=Ack)
async def amend_suborder(
    position_ref: str,
    sub_order_ref: str,
    request: AmendSubOrderRequest,
    db: AsyncSession = Depends(get_db)
) -> Ack:
    """Amend a specific TP/SL leg"""
    try:
        # TODO: Implement suborder amendment logic
        return Ack(
            status="ACK",
            received_at="2024-01-15T10:30:00Z",  # TODO: Use actual timestamp
            position_ref=position_ref,
            sub_order_ref=sub_order_ref
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{position_ref}/suborders/{sub_order_ref}/cancel", response_model=Ack)
async def cancel_suborder(
    position_ref: str,
    sub_order_ref: str,
    request: CancelSubOrderRequest,
    db: AsyncSession = Depends(get_db)
) -> Ack:
    """Cancel a specific TP/SL leg"""
    try:
        # TODO: Implement suborder cancellation logic
        return Ack(
            status="ACK",
            received_at="2024-01-15T10:30:00Z",  # TODO: Use actual timestamp
            position_ref=position_ref,
            sub_order_ref=sub_order_ref
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{position_ref}/close", response_model=Ack)
async def close_position(
    position_ref: str,
    request: ClosePositionRequest,
    db: AsyncSession = Depends(get_db)
) -> Ack:
    """Close a position (ALL / % / FIXED; MARKET or LIMIT)"""
    try:
        from datetime import datetime
        from ...services.position_tracker import position_tracker
        from ...services.orders import order_service
        
        logger.info(f"🔴 Close position request for {position_ref}")
        logger.info(f"📋 Close request: {request}")
        
        # Get the position from the tracker
        position = position_tracker.get_position(position_ref)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position {position_ref} not found"
            )
        
        if position.status != "OPEN":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Position {position_ref} is not open (status: {position.status})"
            )
        
        # Parse close amount
        amount_type = request.amount.get("type")
        amount_value = request.amount.get("value")
        
        if amount_type == "ALL":
            close_quantity = position.size
        elif amount_type == "PERCENTAGE":
            close_quantity = position.size * (amount_value / 100.0)
        elif amount_type == "FIXED":
            close_quantity = amount_value
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid amount type: {amount_type}"
            )
        
        # Ensure we don't close more than the position size
        close_quantity = min(close_quantity, position.size)
        
        if close_quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Close quantity must be greater than 0"
            )
        
        # Parse order details
        order_type = request.order.get("order_type", "MARKET")
        price = request.order.get("price")
        
        if order_type == "LIMIT" and not price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price is required for LIMIT orders"
            )
        
        # Determine close side based on position side
        if position.side == "BUY":
            close_side = "SELL"
        else:
            close_side = "BUY"
        
        # Create close order request
        close_order_request = {
            "idempotency_key": f"close_{position_ref}_{int(datetime.now().timestamp())}",
            "environment": request.environment,
            "source": {
                "strategy_id": position.strategy_id,
                "instance_id": "manual_close",
                "owner": "system"
            },
            "order": {
                "instrument": {
                    "class": "crypto_perp",
                    "symbol": position.symbol
                },
                "side": close_side,
                "quantity": {
                    "type": "contracts",
                    "value": close_quantity
                },
                "order_type": order_type,
                "time_in_force": "IOC",
                "flags": {
                    "post_only": False,
                    "reduce_only": True,
                    "hidden": False,
                    "iceberg": {},
                    "allow_partial_fills": True
                },
                "routing": {
                    "mode": "AUTO"
                },
                "leverage": {
                    "enabled": False
                }
            }
        }
        
        if price:
            close_order_request["order"]["price"] = price
        
        # Place the close order
        logger.info(f"📤 Placing close order: {close_quantity} {position.symbol} {close_side} @ {order_type}")
        
        # Convert dict to CreateOrderRequest
        from ...schemas.orders import CreateOrderRequest
        close_request = CreateOrderRequest(**close_order_request)
        
        result, ack, error = await order_service.create_order(close_request, db)
        
        if result.success:
            logger.info(f"✅ Close order placed successfully: {result.order_ref}")
            return Ack(
                status="ACK",
                received_at=datetime.now().isoformat(),
                position_ref=position_ref,
                order_ref=result.order_ref
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to place close order: {result.error}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error closing position {position_ref}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{position_ref}", response_model=PositionView)
async def get_position(
    position_ref: str,
    db: AsyncSession = Depends(get_db)
) -> PositionView:
    """Fetch a position (OPEN/CLOSING/CLOSED)"""
    try:
        # TODO: Implement position retrieval logic
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/", response_model=ListPositionsResponse)
async def list_positions(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_id: Optional[str] = Query(None, description="Filter by strategy ID"),
    db: AsyncSession = Depends(get_db)
) -> ListPositionsResponse:
    """List positions filtered by symbol & strategy"""
    try:
        # TODO: Implement position listing logic
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
