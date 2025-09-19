"""
Core order service for COM backend
Handles order creation, validation, and routing
"""
import logging
import uuid
import json
import time
import csv
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..schemas.orders import (
    CreateOrderRequest, OrderCreateResult, 
    AmendOrderRequestWrapper, OrderAmendResult,
    CancelOrderRequest, OrderCancelResult
)
from ..schemas.base import (
    OrderRequest, OrderView, OrderState, 
    Ack, ErrorEnvelope, Environment
)
from ..core.database import Order, Position, generate_order_ref, generate_position_ref
from .position_tracker import OrderStatus, OrderType
from ..adapters.manager import broker_manager
from ..storage.idempotency import idempotency_service, create_duplicate_intent_error

logger = logging.getLogger(__name__)

class OrderService:
    """Core order management service"""
    
    def __init__(self):
        self.logger = logger
    
    async def create_order(
        self, 
        request: CreateOrderRequest, 
        db: AsyncSession
    ) -> Tuple[OrderCreateResult, Optional[Ack], Optional[ErrorEnvelope]]:
        """Create a new order"""
        start_time = time.time()
        try:
            # Check idempotency
            idempotency_start = time.time()
            idempotency_result = await idempotency_service.check_idempotency(
                db, 
                request.idempotency_key, 
                "CREATE_ORDER", 
                request.model_dump()
            )
            idempotency_time = (time.time() - idempotency_start) * 1000
            logger.info(f"⏱️  Idempotency check: {idempotency_time:.2f}ms")
            
            if idempotency_result[0]:  # exists
                if idempotency_result[1]:  # same payload
                    # Return stored result
                    stored_data = idempotency_result[1]
                    ack = Ack(
                        status="ACK",
                        received_at=datetime.utcnow(),
                        environment=request.environment,
                        order_ref=stored_data.get("order_ref"),
                        position_ref=stored_data.get("position_ref"),
                        adjustments=stored_data.get("adjustments")
                    )
                    return OrderCreateResult(
                        success=True,
                        order_ref=stored_data.get("order_ref"),
                        position_ref=stored_data.get("position_ref"),
                        broker_order_id=stored_data.get("broker_order_id"),
                        adjustments=stored_data.get("adjustments")
                    ), ack, None
                else:
                    # Duplicate intent
                    error = create_duplicate_intent_error(
                        request.idempotency_key,
                        idempotency_result[2] or "unknown"
                    )
                    return OrderCreateResult(
                        success=False, 
                        error="Duplicate intent", 
                        error_code="DUPLICATE_INTENT"
                    ), None, error
            
            # Validate request
            validation_start = time.time()
            validation_result = await self._validate_order_request(request)
            validation_time = (time.time() - validation_start) * 1000
            logger.info(f"⏱️  Order validation: {validation_time:.2f}ms")
            
            if not validation_result["valid"]:
                error = ErrorEnvelope(
                    error={
                        "code": "INVALID_SCHEMA",
                        "message": f"Order validation failed: {', '.join(validation_result['errors'])}",
                        "idempotency_key": request.idempotency_key,
                        "details": {"errors": validation_result["errors"]}
                    }
                )
                return OrderCreateResult(
                    success=False, 
                    error="Validation failed", 
                    error_code="INVALID_SCHEMA"
                ), None, error
            
            # Generate order reference
            order_ref = generate_order_ref()
            
            # Calculate quantity from risk sizing if needed
            if request.order.risk and request.order.risk.sizing:
                # Convert environment to string format
                environment_str = "paper" if request.environment.sandbox else "live"
                quantity_result = await self._calculate_quantity_from_risk_sizing(
                    request.order, 
                    request.source.strategy_id,
                    environment_str
                )
                if not quantity_result["success"]:
                    error = ErrorEnvelope(
                        error={
                            "code": "RISK_SIZING_ERROR",
                            "message": f"Risk sizing calculation failed: {quantity_result['error']}",
                            "idempotency_key": request.idempotency_key,
                            "details": {"risk_sizing_error": quantity_result["error"]}
                        }
                    )
                    return OrderCreateResult(
                        success=False, 
                        error="Risk sizing failed", 
                        error_code="RISK_SIZING_ERROR"
                    ), None, error
                
                # Update the order with calculated quantity
                request.order.quantity = quantity_result["quantity"]
                logger.info(f"💰 Calculated quantity from risk sizing: {request.order.quantity.value} {request.order.quantity.type}")
            
            # Snap prices and quantities to tick/lot sizes
            adjustments = await self._snap_order_parameters(request.order)
            
            # Route order to broker
            routing_result = await self._route_order(request.order, request.environment)
            if not routing_result["success"]:
                error = ErrorEnvelope(
                    error={
                        "code": "ROUTING_UNAVAILABLE",
                        "message": f"Order routing failed: {routing_result['error']}",
                        "idempotency_key": request.idempotency_key,
                        "details": {"routing_error": routing_result["error"]}
                    }
                )
                return OrderCreateResult(
                    success=False, 
                    error="Routing failed", 
                    error_code="ROUTING_UNAVAILABLE"
                ), None, error
            
            # Place order with broker
            logger.info(f"🚀 Placing order with broker: {routing_result['broker']}")
            broker_start = time.time()
            broker_result = await self._place_order_with_broker(
                request.order, 
                routing_result["broker"], 
                adjustments
            )
            broker_time = (time.time() - broker_start) * 1000
            logger.info(f"⏱️  Broker placement: {broker_time:.2f}ms")
            logger.info(f"📊 Broker placement result: {broker_result}")
            
            if broker_result["success"]:
                # Create or update position
                position_ref = await self._create_or_update_position(
                    db,
                    request.source.strategy_id,
                    request.order.instrument.symbol,
                    request.order.side,
                    request.order.quantity.value if request.order.quantity else None
                )
                
                # Store order in database
                order = Order(
                    order_ref=order_ref,
                    strategy_id=request.source.strategy_id,
                    instance_id=request.source.instance_id,
                    owner=request.source.owner,
                    symbol=request.order.instrument.symbol,
                    instrument_class=request.order.instrument.class_.value,
                    side=request.order.side.value,
                    order_type=request.order.order_type.value,
                    quantity=request.order.quantity.value if request.order.quantity else 0,
                    price=request.order.price,
                    stop_price=request.order.stop_price,
                    time_in_force=request.order.time_in_force.value,
                    expire_at=request.order.expire_at,
                    post_only=request.order.flags.post_only,
                    reduce_only=request.order.flags.reduce_only,
                    hidden=request.order.flags.hidden,
                    allow_partial_fills=request.order.flags.allow_partial_fills,
                    state=OrderState.NEW.value,
                    broker=routing_result["broker"],
                    broker_order_id=broker_result["broker_order_id"],
                    risk_config=json.dumps(request.order.risk.model_dump()) if request.order.risk else None,
                    routing_config=json.dumps(request.order.routing.model_dump()),
                    leverage_config=json.dumps(request.order.leverage.model_dump()),
                    exit_plan=json.dumps(request.order.exit_plan.model_dump()) if request.order.exit_plan else None,
                    position_ref=position_ref
                )
                
                db_start = time.time()
                db.add(order)
                await db.commit()
                db_time = (time.time() - db_start) * 1000
                logger.info(f"⏱️  Database save: {db_time:.2f}ms")
                
                # Store idempotency record
                idempotency_store_start = time.time()
                await idempotency_service.store_idempotency(
                    db,
                    request.idempotency_key,
                    "CREATE_ORDER",
                    request.model_dump(),
                    order_ref,
                    {
                        "order_ref": order_ref,
                        "position_ref": position_ref,
                        "broker_order_id": broker_result["broker_order_id"],
                        "adjustments": adjustments
                    }
                )
                idempotency_store_time = (time.time() - idempotency_store_start) * 1000
                logger.info(f"⏱️  Idempotency storage: {idempotency_store_time:.2f}ms")
                
                # Add position and order tracking
                if broker_result["success"]:
                    try:
                        from .position_tracker import position_tracker, OrderType
                        from ..adapters.manager import broker_manager
                        
                        # Get broker adapter to retrieve position ID
                        broker_name = "mexc"
                        await broker_manager.ensure_broker_connected(broker_name)
                        broker = broker_manager.get_adapter(broker_name)
                        
                        # Get position ID from filled order
                        broker_position_id = None
                        if broker:
                            order_details = await broker.get_order(broker_result["broker_order_id"])
                            if order_details and order_details.get("broker_data"):
                                broker_position_id = order_details["broker_data"].positionId
                        
                        # Add position for tracking
                        position_id = position_tracker.add_position(
                            broker_position_id=broker_position_id,
                            symbol=request.order.instrument.symbol,
                            side=request.order.side,
                            size=request.order.quantity.value,
                            entry_price=0.0,  # Will be updated when we get fill price
                            strategy_id=request.source.strategy_id,
                            order_ref=order_ref
                        )
                        
                        # Add entry order for tracking
                        entry_order_id = position_tracker.add_order(
                            broker_order_id=broker_result["broker_order_id"],
                            parent_position_id=position_id,
                            order_type=OrderType.ENTRY,
                            side=request.order.side,
                            quantity=request.order.quantity.value,
                            price=request.order.price or 0.0,
                            strategy_id=request.source.strategy_id,
                            order_ref=order_ref
                        )
                        
                        logger.info(f"📊 Position tracking: {position_id}, Entry order: {entry_order_id}")
                        
                        # Send GUI event for new order
                        await self._send_gui_order_event(order, "ORDER_CREATED")
                        
                        # Log order to data logger
                        await self._log_order_data(request, broker_result, order_ref)
                        
                    except Exception as e:
                        logger.error(f"❌ Error setting up position tracking: {e}")
                
                # Handle post-only TP orders immediately after position creation
                exit_plan_orders = []
                if request.order.exit_plan and broker_result["success"]:
                    try:
                        logger.info(f"🚀 Attempting to handle exit plan legs immediately for order {order_ref}")
                        await self._handle_post_only_tp_immediately(request.order, order, broker_result["broker_order_id"], request)
                        logger.info(f"✅ Exit plan legs handling completed for order {order_ref}")
                    except Exception as e:
                        logger.error(f"❌ Error handling post-only TP immediately: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Log attached TP/SL orders to CSV (non-post-only legs that are attached to main order)
                    try:
                        logger.info(f"🚀 Logging attached TP/SL orders for order {order_ref}")
                        await self._log_attached_tp_sl_orders(request.order, order, broker_result["broker_order_id"], request)
                        logger.info(f"✅ Attached TP/SL logging completed for order {order_ref}")
                    except Exception as e:
                        logger.error(f"❌ Error logging attached TP/SL orders: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                
                # Add order to monitoring only if it has advanced features that need manual execution
                needs_monitoring = await self._order_needs_monitoring(request.order, exit_plan_orders)
                if needs_monitoring:
                    try:
                        from .order_monitor import order_monitor
                        # Pass stop limit order ID if available
                        stop_limit_order_id = broker_result.get("stop_limit_order_id")
                        await order_monitor.add_order_for_monitoring(order, original_request=request, stop_limit_order_id=stop_limit_order_id)
                        logger.info(f"Order {order.order_ref} added to monitoring for manual execution")
                    except Exception as e:
                        logger.warning(f"Failed to add order to monitoring: {e}")
                else:
                    logger.info(f"Order {order.order_ref} does not need monitoring - all features handled by broker")
                
                # Create ACK response with exit plan order details
                ack = Ack(
                    status="ACK",
                    received_at=datetime.utcnow(),
                    environment=request.environment,
                    order_ref=order_ref,
                    position_ref=position_ref,
                    adjustments=adjustments
                )
                
                # Add exit plan order information to adjustments if any were created
                if exit_plan_orders:
                    if not hasattr(ack, 'adjustments'):
                        ack.adjustments = {}
                    ack.adjustments["exit_plan_orders"] = exit_plan_orders
                
                result = OrderCreateResult(
                    success=True,
                    order_ref=order_ref,
                    position_ref=position_ref,
                    broker_order_id=broker_result["broker_order_id"],
                    adjustments=adjustments
                )
                
                total_time = (time.time() - start_time) * 1000
                logger.info(f"⏱️  TOTAL ORDER PROCESSING: {total_time:.2f}ms")
                return result, ack, None
            else:
                error = ErrorEnvelope(
                    error={
                        "code": "BROKER_DOWN",
                        "message": f"Broker order placement failed: {broker_result['error']}",
                        "idempotency_key": request.idempotency_key,
                        "details": {"broker_error": broker_result["error"]}
                    }
                )
                return OrderCreateResult(
                    success=False, 
                    error="Broker placement failed", 
                    error_code="BROKER_DOWN"
                ), None, error
                
        except Exception as e:
            self.logger.error(f"Error creating order: {e}")
            await db.rollback()
            error = ErrorEnvelope(
                error={
                    "code": "INTERNAL_ERROR",
                    "message": f"Internal server error: {str(e)}",
                    "idempotency_key": request.idempotency_key
                }
            )
            return OrderCreateResult(
                success=False, 
                error="Internal error", 
                error_code="INTERNAL_ERROR"
            ), None, error
    
    async def amend_order(
        self, 
        order_ref: str, 
        request: AmendOrderRequestWrapper,
        db: AsyncSession
    ) -> Tuple[OrderAmendResult, Optional[Ack], Optional[ErrorEnvelope]]:
        """Amend an existing order"""
        try:
            # Check idempotency
            idempotency_result = await idempotency_service.check_idempotency(
                db, 
                request.idempotency_key, 
                "AMEND_ORDER", 
                request.model_dump()
            )
            
            if idempotency_result[0]:  # exists
                if idempotency_result[1]:  # same payload
                    # Return stored result
                    stored_data = idempotency_result[1]
                    ack = Ack(
                        status="ACK",
                        received_at=datetime.utcnow(),
                        environment=request.environment,
                        order_ref=order_ref
                    )
                    return OrderAmendResult(
                        success=True,
                        order_ref=order_ref
                    ), ack, None
                else:
                    # Duplicate intent
                    error = create_duplicate_intent_error(
                        request.idempotency_key,
                        idempotency_result[2] or "unknown"
                    )
                    return OrderAmendResult(
                        success=False, 
                        error="Duplicate intent", 
                        error_code="DUPLICATE_INTENT"
                    ), None, error
            
            # Get existing order
            result = await db.execute(
                select(Order).where(Order.order_ref == order_ref)
            )
            order = result.scalar_one_or_none()
            
            if not order:
                error = ErrorEnvelope(
                    error={
                        "code": "POSITION_NOT_FOUND",
                        "message": f"Order {order_ref} not found",
                        "idempotency_key": request.idempotency_key
                    }
                )
                return OrderAmendResult(
                    success=False, 
                    error="Order not found", 
                    error_code="POSITION_NOT_FOUND"
                ), None, error
            
            # TODO: Implement order amendment logic
            # This would involve:
            # 1. Validating the changes
            # 2. Sending amendment to broker
            # 3. Updating local state
            
            error = ErrorEnvelope(
                error={
                    "code": "UNSUPPORTED_FEATURE",
                    "message": "Order amendment not yet implemented",
                    "idempotency_key": request.idempotency_key
                }
            )
            return OrderAmendResult(
                success=False, 
                error="Not implemented", 
                error_code="UNSUPPORTED_FEATURE"
            ), None, error
            
        except Exception as e:
            self.logger.error(f"Error amending order: {e}")
            await db.rollback()
            error = ErrorEnvelope(
                error={
                    "code": "INTERNAL_ERROR",
                    "message": f"Internal server error: {str(e)}",
                    "idempotency_key": request.idempotency_key
                }
            )
            return OrderAmendResult(
                success=False, 
                error="Internal error", 
                error_code="INTERNAL_ERROR"
            ), None, error
    
    async def cancel_order(
        self, 
        order_ref: str, 
        request: CancelOrderRequest,
        db: AsyncSession
    ) -> Tuple[OrderCancelResult, Optional[Ack], Optional[ErrorEnvelope]]:
        """Cancel an existing order"""
        try:
            # Check idempotency
            idempotency_result = await idempotency_service.check_idempotency(
                db, 
                request.idempotency_key, 
                "CANCEL_ORDER", 
                request.model_dump()
            )
            
            if idempotency_result[0]:  # exists
                if idempotency_result[1]:  # same payload
                    # Return stored result
                    stored_data = idempotency_result[1]
                    ack = Ack(
                        status="ACK",
                        received_at=datetime.utcnow(),
                        environment=request.environment,
                        order_ref=order_ref
                    )
                    return OrderCancelResult(
                        success=True,
                        order_ref=order_ref
                    ), ack, None
                else:
                    # Duplicate intent
                    error = create_duplicate_intent_error(
                        request.idempotency_key,
                        idempotency_result[2] or "unknown"
                    )
                    return OrderCancelResult(
                        success=False, 
                        error="Duplicate intent", 
                        error_code="DUPLICATE_INTENT"
                    ), None, error
            
            # Get existing order
            result = await db.execute(
                select(Order).where(Order.order_ref == order_ref)
            )
            order = result.scalar_one_or_none()
            
            if not order:
                error = ErrorEnvelope(
                    error={
                        "code": "POSITION_NOT_FOUND",
                        "message": f"Order {order_ref} not found",
                        "idempotency_key": request.idempotency_key
                    }
                )
                return OrderCancelResult(
                    success=False, 
                    error="Order not found", 
                    error_code="POSITION_NOT_FOUND"
                ), None, error
            
            # TODO: Implement order cancellation logic
            # This would involve:
            # 1. Sending cancellation to broker
            # 2. Updating local state
            
            # Remove order from monitoring if it was being monitored
            try:
                from .order_monitor import order_monitor
                if order_monitor.is_monitoring(order_ref):
                    order_monitor.remove_order_from_monitoring(order_ref)
                    logger.info(f"Order {order_ref} removed from monitoring due to cancellation")
            except Exception as e:
                logger.warning(f"Failed to remove order from monitoring: {e}")
            
            error = ErrorEnvelope(
                error={
                    "code": "UNSUPPORTED_FEATURE",
                    "message": "Order cancellation not yet implemented",
                    "idempotency_key": request.idempotency_key
                }
            )
            return OrderCancelResult(
                success=False, 
                error="Not implemented", 
                error_code="UNSUPPORTED_FEATURE"
            ), None, error
            
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
            await db.rollback()
            error = ErrorEnvelope(
                error={
                    "code": "INTERNAL_ERROR",
                    "message": f"Internal server error: {str(e)}",
                    "idempotency_key": request.idempotency_key
                }
            )
            return OrderCancelResult(
                success=False, 
                error="Internal error", 
                error_code="INTERNAL_ERROR"
            ), None, error
    
    async def get_order(self, order_ref: str, db: AsyncSession) -> Optional[OrderView]:
        """Get order details"""
        try:
            result = await db.execute(
                select(Order).where(Order.order_ref == order_ref)
            )
            order = result.scalar_one_or_none()
            
            if not order:
                return None
            
            # Convert to OrderView
            # TODO: Implement proper conversion
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting order: {e}")
            return None
    
    # ============================================================================
    # PRIVATE METHODS
    # ============================================================================
    
    async def _validate_order_request(self, request: CreateOrderRequest) -> Dict[str, Any]:
        """Validate order request"""
        errors = []
        warnings = []
        
        # Basic validation
        if not request.source.strategy_id:
            errors.append("Missing strategy_id")
        
        if not request.order.instrument.symbol:
            errors.append("Missing instrument symbol")
        
        # Order type validation
        if request.order.order_type.value in ["LIMIT", "STOP_LIMIT"] and not request.order.price:
            errors.append(f"{request.order.order_type.value} orders require price")
        
        if request.order.order_type.value in ["STOP", "STOP_LIMIT"] and not request.order.stop_price:
            errors.append(f"{request.order.order_type.value} orders require stop_price")
        
        # Quantity vs risk.sizing validation
        has_quantity = request.order.quantity is not None
        has_risk_sizing = request.order.risk is not None and request.order.risk.sizing is not None
        
        if has_quantity == has_risk_sizing:
            errors.append("Exactly one of quantity or risk.sizing must be provided")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def _snap_order_parameters(self, order: OrderRequest) -> Optional[Dict[str, Any]]:
        """Snap order parameters to valid tick/lot sizes"""
        adjustments = {}
        
        # Get broker adapter for symbol
        broker = await self._get_broker_for_symbol(order.instrument.symbol)
        if not broker:
            return None
        
        # Snap price if provided
        if order.price:
            original_price = order.price
            snapped_price = broker.snap_to_tick(order.price, order.instrument.symbol)
            if snapped_price != original_price:
                adjustments["price_snapped_to"] = snapped_price
                order.price = snapped_price
        
        # Snap quantity if provided
        if order.quantity:
            original_qty = order.quantity.value
            snapped_qty = broker.snap_to_lot(order.quantity.value, order.instrument.symbol)
            if snapped_qty != original_qty:
                adjustments["qty_snapped_to"] = snapped_qty
                order.quantity.value = snapped_qty
        
        return adjustments if adjustments else None
    
    async def _calculate_quantity_from_risk_sizing(self, order: OrderRequest, strategy_id: str, environment: str) -> Dict[str, Any]:
        """Calculate order quantity from risk sizing configuration"""
        try:
            from ..schemas.base import Quantity
            from ..services.balance_tracker import balance_tracker
            from ..adapters.manager import broker_manager
            
            sizing = order.risk.sizing
            mode = sizing.mode
            value = sizing.value  # Percentage value (e.g., 25 for 25%)
            
            logger.info(f"💰 Calculating quantity from risk sizing: {mode} = {value}% (environment: {environment})")
            
            # Get balance data based on mode and environment
            if mode == "PCT_BALANCE":
                # Get total balance across all strategies
                balance_data = await balance_tracker.get_total_balance()
                available_balance = balance_data.get("total_available", 0.0)
                logger.info(f"💰 Total available balance: {available_balance}")
                
            elif mode == "PCT_BROKER":
                # Get balance for specific broker
                broker = sizing.broker or "mexc"  # Default to mexc
                
                # Get broker-specific balance based on environment
                if environment == "paper":
                    # For paper trading, use testnet balance
                    broker_adapter = broker_manager.get_adapter(broker)
                    if broker_adapter and hasattr(broker_adapter, 'get_balances'):
                        broker_balances = await broker_adapter.get_balances()
                        available_balance = broker_balances.get('USDT', 0.0)
                        logger.info(f"💰 Paper trading - Broker ({broker}) testnet balance: {available_balance}")
                    else:
                        # Fallback to total balance
                        balance_data = await balance_tracker.get_total_balance()
                        available_balance = balance_data.get("total_available", 0.0)
                        logger.info(f"💰 Paper trading - Fallback to total balance: {available_balance}")
                else:
                    # For live trading, use live balance
                    broker_adapter = broker_manager.get_adapter(broker)
                    if broker_adapter and hasattr(broker_adapter, 'get_balances'):
                        broker_balances = await broker_adapter.get_balances()
                        available_balance = broker_balances.get('USDT', 0.0)
                        logger.info(f"💰 Live trading - Broker ({broker}) live balance: {available_balance}")
                    else:
                        # Fallback to total balance
                        balance_data = await balance_tracker.get_total_balance()
                        available_balance = balance_data.get("total_available", 0.0)
                        logger.info(f"💰 Live trading - Fallback to total balance: {available_balance}")
                
            elif mode == "PCT_ALL":
                # Same as PCT_BALANCE for now
                balance_data = await balance_tracker.get_total_balance()
                available_balance = balance_data.get("total_available", 0.0)
                logger.info(f"💰 All accounts available balance: {available_balance}")
                
            elif mode == "PCT_MARKET":
                # Get balance for specific market
                market = sizing.market or "crypto"  # Default to crypto
                balance_data = await balance_tracker.get_total_balance()
                market_summary = balance_data.get("market_summary", {})
                market_data = market_summary.get(market, {})
                available_balance = market_data.get("balance", 0.0)
                logger.info(f"💰 Market ({market}) available balance: {available_balance}")
                
            elif mode == "USD":
                # Direct USD amount
                available_balance = value
                value = 100.0  # 100% of the specified USD amount
                logger.info(f"💰 Direct USD amount: {available_balance}")
                
            else:
                return {
                    "success": False,
                    "error": f"Unsupported risk sizing mode: {mode}"
                }
            
            # Calculate notional value (USD amount to trade)
            notional_value = available_balance * (value / 100.0)
            logger.info(f"💰 Calculated notional value: {notional_value} USD ({value}% of {available_balance})")
            
            # Apply caps and floors if specified
            if sizing.cap:
                max_notional = sizing.cap.get("notional")
                if max_notional and notional_value > max_notional:
                    notional_value = max_notional
                    logger.info(f"💰 Capped notional value to: {notional_value}")
            
            if sizing.floor:
                min_notional = sizing.floor.get("notional")
                if min_notional and notional_value < min_notional:
                    notional_value = min_notional
                    logger.info(f"💰 Floored notional value to: {notional_value}")
            
            # Convert notional value to quantity based on order type
            if order.order_type.value in ["MARKET", "LIMIT"]:
                # For market/limit orders, we need to convert USD to token quantity
                # This requires current market price
                
                # Get current price from order or fetch from market data
                if order.price:
                    # LIMIT orders have price specified
                    current_price = order.price
                    logger.info(f"💰 Using order price for quantity calculation: ${current_price}")
                else:
                    # MARKET orders need current market price
                    try:
                        from .mexc_market_data import mexc_market_data
                        market_data = await mexc_market_data.get_market_data(order.instrument.symbol)
                        if market_data and 'last_price' in market_data:
                            current_price = float(market_data['last_price'])
                            logger.info(f"💰 Using market price for quantity calculation: ${current_price}")
                        else:
                            current_price = 1.0
                            logger.warning(f"💰 Could not get market price for {order.instrument.symbol}, using fallback: ${current_price}")
                    except Exception as e:
                        current_price = 1.0
                        logger.warning(f"💰 Error getting market price for {order.instrument.symbol}: {e}, using fallback: ${current_price}")
                
                # Calculate quantity in tokens (e.g., DOGE)
                quantity_value = notional_value / current_price
                
                # Create quantity object (in tokens, will be converted to contracts by broker adapter)
                quantity = Quantity(
                    type="base_units",  # This represents tokens (e.g., DOGE)
                    value=quantity_value
                )
                
                logger.info(f"💰 Calculated quantity: {quantity_value} tokens (${notional_value} / ${current_price})")
                
            else:
                return {
                    "success": False,
                    "error": f"Risk sizing not supported for order type: {order.order_type.value}"
                }
            
            return {
                "success": True,
                "quantity": quantity,
                "notional_value": notional_value,
                "available_balance": available_balance
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating quantity from risk sizing: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _route_order(self, order: OrderRequest, environment: Environment) -> Dict[str, Any]:
        """Route order to appropriate broker"""
        try:
            # For now, route to first available broker
            # TODO: Implement proper routing logic based on:
            # - Routing mode (AUTO vs DIRECT)
            # - Broker availability
            # - Environment (paper vs live)
            # - Symbol support
            
            available_brokers = broker_manager.get_enabled_brokers()
            if not available_brokers:
                return {
                    "success": False,
                    "error": "No brokers available",
                    "broker": None
                }
            
            # Get first available broker
            broker_name = list(available_brokers.keys())[0]
            broker_adapter = broker_manager.get_adapter(broker_name)
            
            # Check if broker supports the symbol
            if not await self._broker_supports_symbol(broker_adapter, order.instrument.symbol):
                return {
                    "success": False,
                    "error": f"Broker {broker_name} does not support symbol {order.instrument.symbol}",
                    "broker": None
                }
            
            return {
                "success": True,
                "broker": broker_name,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Routing error: {str(e)}",
                "broker": None
            }
    
    async def _place_order_with_broker(self, order: OrderRequest, broker_name: str, adjustments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Place order with specific broker"""
        try:
            broker = broker_manager.get_adapter(broker_name)
            if not broker:
                return {
                    "success": False,
                    "error": f"Broker {broker_name} not found",
                    "broker_order_id": None
                }
            
            # Place order with broker directly (broker adapters expect OrderRequest objects)
            result = await broker.place_order(order)
            logger.info(f"📊 Broker order result: {result}")
            
            if result["success"]:
                logger.info(f"✅ Broker order placement successful: {result}")
                return {
                    "success": True,
                    "broker_order_id": result["broker_order_id"],
                    "error": None
                }
            else:
                logger.error(f"❌ Broker order placement failed: {result}")
                if "details" in result:
                    logger.error(f"📋 Broker error details: {result['details']}")
                return {
                    "success": False,
                    "error": result["error"],
                    "broker_order_id": None
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Broker placement error: {str(e)}",
                "broker_order_id": None
            }
    

    
    async def _create_or_update_position(
        self, 
        db: AsyncSession,
        strategy_id: str, 
        symbol: str, 
        side: str, 
        quantity: Optional[float]
    ) -> str:
        """Create or update position"""
        try:
            # Check for existing position
            result = await db.execute(
                select(Position).where(
                    Position.strategy_id == strategy_id,
                    Position.symbol == symbol,
                    Position.state == "OPEN"
                )
            )
            existing_position = result.scalar_one_or_none()
            
            if existing_position:
                # Update existing position
                # TODO: Implement position update logic
                return existing_position.position_ref
            else:
                # Create new position
                position_ref = generate_position_ref()
                position = Position(
                    position_ref=position_ref,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    state="OPEN"
                )
                
                db.add(position)
                await db.commit()
                
                return position_ref
                
        except Exception as e:
            self.logger.error(f"Error creating/updating position: {e}")
            await db.rollback()
            # Generate a temporary reference
            return generate_position_ref()
    
    async def _get_broker_for_symbol(self, symbol: str):
        """Get broker adapter for symbol"""
        # TODO: Implement symbol-to-broker mapping
        # This would involve checking which brokers support the symbol
        
        available_brokers = broker_manager.get_enabled_brokers()
        if available_brokers:
            broker_name = list(available_brokers.keys())[0]
            return broker_manager.get_adapter(broker_name)
        return None
    
    async def _broker_supports_symbol(self, broker, symbol: str) -> bool:
        """Check if broker supports symbol"""
        try:
            market_info = await broker.get_market_info(symbol)
            return bool(market_info)
        except:
            return False
    
    async def _create_exit_plan_orders(self, order_request, parent_order_ref: str, broker_name: str) -> List[Dict[str, Any]]:
        """Create actual TP/SL orders from exit plan and send them to broker"""
        try:
            if not order_request.exit_plan or not order_request.exit_plan.legs:
                return []
            
            # Debug: Print the exit plan structure
            logger.info(f"🔍 Exit plan structure: {order_request.exit_plan}")
            logger.info(f"🔍 Exit plan legs: {order_request.exit_plan.legs}")
            logger.info(f"🔍 First leg type: {type(order_request.exit_plan.legs[0]) if order_request.exit_plan.legs else 'No legs'}")
            
            broker = broker_manager.get_adapter(broker_name)
            if not broker:
                logger.error(f"Broker {broker_name} not available for exit plan orders")
                return []
            
            created_orders = []
            
            for leg in (order_request.exit_plan.legs or []):
                if not hasattr(leg, 'kind') or not leg.kind or leg.kind.value not in ["TP", "SL"]:
                    logger.warning(f"Skipping unsupported exit plan leg type: {leg.kind.value}")
                    continue
                
                # Create STOP order for this leg
                stop_order = self._create_stop_order_from_leg(order_request, leg, parent_order_ref)
                
                # Send to broker
                try:
                    result = await broker.place_order(stop_order)
                    if result["success"]:
                        created_orders.append({
                            "leg_kind": leg.kind.value,
                            "broker_order_id": result["broker_order_id"],
                            "trigger_price": leg.trigger["value"],
                            "status": "CREATED"
                        })
                        logger.info(f"✅ Created {leg.kind.value} order: {result['broker_order_id']} at {leg.trigger['value']}")
                    else:
                        logger.error(f"❌ Failed to create {leg.kind.value} order: {result['error']}")
                        created_orders.append({
                            "leg_kind": leg.kind.value,
                            "error": result["error"],
                            "status": "FAILED"
                        })
                except Exception as e:
                    logger.error(f"❌ Exception creating {leg.kind.value} order: {e}")
                    created_orders.append({
                        "leg_kind": leg.kind.value,
                        "error": str(e),
                        "status": "FAILED"
                    })
            
            return created_orders
            
        except Exception as e:
            logger.error(f"Error creating exit plan orders: {e}")
            return []
    
    def _create_stop_order_from_leg(self, parent_order, leg, parent_order_ref: str):
        """Create a STOP order from an exit plan leg"""
        from ..schemas.orders import OrderRequest
        from ..schemas.base import Instrument, Quantity, Flags, Routing, Leverage
        
        # Determine order side based on parent order and leg type
        if leg.kind == "TP":
            # Take profit: if parent is BUY, we need to SELL
            side = "SELL" if parent_order.side == "BUY" else "BUY"
        else:  # SL
            # Stop loss: if parent is BUY, we need to SELL
            side = "SELL" if parent_order.side == "BUY" else "BUY"
        
        # Calculate quantity based on allocation
        if leg.allocation["type"] == "percentage":
            quantity_value = parent_order.quantity.value * (leg.allocation["value"] / 100.0)
        else:
            quantity_value = leg.allocation["value"]
        
        # Create the STOP order with proper TP/SL indication
        stop_order = OrderRequest(
            instrument=parent_order.instrument,
            side=side,
            quantity=Quantity(
                type=parent_order.quantity.type,
                value=quantity_value
            ),
            order_type="STOP",
            stop_price=leg.trigger["value"],
            time_in_force=leg.exec["time_in_force"],
            flags=Flags(
                post_only=False,  # STOP orders can't be post-only
                reduce_only=True,  # Exit plan orders should reduce position
                hidden=False,
                iceberg={},
                allow_partial_fills=True
            ),
            routing=Routing(mode="DIRECT", direct={"broker": "mexc"}),  # Default to mexc
            leverage=parent_order.leverage
        )
        
        # Add metadata to indicate TP vs SL for the MEXC adapter
        stop_order._leg_kind = leg.kind.value  # Add metadata for adapter to use
        
        return stop_order
    
    async def _order_needs_monitoring(self, order_request, exit_plan_orders: List[Dict[str, Any]]) -> bool:
        """Determine if an order needs internal monitoring"""
        # Check if order has advanced features that broker doesn't support
        advanced_features = []

        logger.debug(f"Checking if order needs monitoring: type={type(order_request)}, has_exit_plan={hasattr(order_request, 'exit_plan') and order_request.exit_plan}")

        # Check for post-only flag
        if order_request.flags.post_only:
            advanced_features.append("post_only")

        # Check for iceberg orders
        if order_request.flags.iceberg and order_request.flags.iceberg.get("enabled"):
            advanced_features.append("iceberg")

                # Check for advanced exit plan features
        if order_request.exit_plan and order_request.exit_plan.legs:
            logger.info(f"🔍 Exit plan has {len(order_request.exit_plan.legs)} legs")
            for i, leg in enumerate(order_request.exit_plan.legs or []):
                logger.info(f"🔍 Leg {i+1}: kind={leg.kind}, after_fill_actions={getattr(leg, 'after_fill_actions', None)}")
                # Check for trailing stops
                if leg.kind == "TRAILING_SL":
                    advanced_features.append("trailing_stop")
                if hasattr(leg, 'after_fill_actions') and leg.after_fill_actions:
                    for action_data in leg.after_fill_actions:
                        if isinstance(action_data, dict) and action_data.get('action') == "START_TRAILING_SL":
                            advanced_features.append("trailing_stop_after_fill")
                        if isinstance(action_data, dict) and action_data.get('action') == "SET_SL_TO_BREAKEVEN":
                            advanced_features.append("sl_breakeven_after_fill")

                # Check for post-only orders (both TP and SL need monitoring)
                if hasattr(leg, 'exec') and leg.exec:
                    exec_config = leg.exec
                    is_post_only = False
                    if isinstance(exec_config, dict) and exec_config.get('post_only'):
                        is_post_only = True
                    elif hasattr(exec_config, 'post_only') and exec_config.post_only:
                        is_post_only = True

                    if is_post_only:
                        if leg.kind == "TP":
                            advanced_features.append("post_only_tp")
                        elif leg.kind == "SL":
                            advanced_features.append("post_only_sl")

                # Only monitor TP/SL legs that need special handling
                # - Post-only TP/SL legs are handled immediately by _handle_post_only_tp_immediately
                # - Non-post-only TP/SL legs are attached directly to the main order by MEXC
                # - Only monitor TP/SL legs with advanced features (like trailing stops)
                if leg.kind in ["TP", "SL"]:
                    # Check if this leg has advanced features that need monitoring
                    has_advanced_features = False
                    
                    # Check for trailing stops
                    if leg.kind == "TRAILING_SL":
                        has_advanced_features = True
                    if hasattr(leg, 'after_fill_actions') and leg.after_fill_actions:
                        for action_data in leg.after_fill_actions:
                            if isinstance(action_data, dict) and action_data.get('action') == "START_TRAILING_SL":
                                has_advanced_features = True
                            if isinstance(action_data, dict) and action_data.get('action') == "SET_SL_TO_BREAKEVEN":
                                has_advanced_features = True
                    
                    # Check if this leg is post-only (needs separate handling)
                    is_post_only = False
                    if hasattr(leg, 'exec') and leg.exec:
                        exec_config = leg.exec
                        if isinstance(exec_config, dict) and exec_config.get('post_only'):
                            is_post_only = True
                        elif hasattr(exec_config, 'post_only') and exec_config.post_only:
                            is_post_only = True
                    
                    # Only monitor if it has advanced features OR is post-only
                    if has_advanced_features or is_post_only:
                        advanced_features.append(f"has_{leg.kind.lower()}_leg")
        
        # Check if any exit plan orders failed to create
        failed_orders = [o for o in exit_plan_orders if o.get("status") == "FAILED"]
        if failed_orders:
            advanced_features.append("failed_exit_plan_orders")
        
        # If no advanced features, broker handles everything
        if not advanced_features:
            logger.info(f"🔍 No advanced features detected, order does not need monitoring")
            return False
        
        logger.info(f"🔍 Order needs monitoring due to advanced features: {advanced_features}")
        return True
    
    async def _handle_post_only_tp_immediately(self, order_request, order, broker_order_id, original_request=None):
        """Handle all exit plan legs as separate orders immediately after position creation"""
        try:
            if not order_request.exit_plan or not order_request.exit_plan.legs:
                return
            
            # Find only TP legs that need to be created as separate orders (post-only LIMIT)
            separate_tp_legs = []
            logger.info(f"🔍 Processing {len(order_request.exit_plan.legs)} exit plan legs")
            for i, leg in enumerate(order_request.exit_plan.legs or []):
                logger.info(f"🔍 Leg {i+1}: kind={leg.kind}, has_exec={hasattr(leg, 'exec')}, exec={getattr(leg, 'exec', None)}")
                if leg.kind == "TP" and hasattr(leg, 'exec') and leg.exec:
                    # Check if this TP is post-only (should be separate)
                    exec_config = leg.exec
                    is_post_only = False
                    if isinstance(exec_config, dict):
                        # Check flags.post_only in the exec config
                        flags = exec_config.get('flags', {})
                        if isinstance(flags, dict) and flags.get('post_only'):
                            is_post_only = True
                    elif hasattr(exec_config, 'post_only') and exec_config.post_only:
                        is_post_only = True
                    
                    if is_post_only:
                        separate_tp_legs.append(leg)
                        logger.info(f"✅ Added post-only TP leg to separate orders list")
                    else:
                        logger.info(f"ℹ️ TP leg is not post-only, will be attached to main order")
                elif leg.kind == "SL":
                    logger.info(f"ℹ️ SL leg will be attached to main order (not separate)")
            
            logger.info(f"🔍 Found {len(separate_tp_legs)} separate TP legs to process")
            if not separate_tp_legs:
                logger.info(f"No separate TP legs to handle for order {order.order_ref}")
                return
            
            logger.info(f"🚀 Placing {len(separate_tp_legs)} separate TP orders after position creation")
            
            # Get broker adapter
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.error(f"Broker {broker_name} not available for post-only TP placement")
                return
            
            # Get position ID from the filled order
            logger.info(f"🔍 Getting position ID from order {broker_order_id}")
            try:
                # Get order details to extract position ID
                order_details = await broker.get_order(broker_order_id)
                if not order_details:
                    logger.error(f"❌ Failed to get order details for {broker_order_id}")
                    return
                
                # Extract position ID from broker data
                broker_data = order_details.get("broker_data")
                if not broker_data or not hasattr(broker_data, 'positionId'):
                    logger.error(f"❌ No position ID found in order details")
                    return
                
                position_id = broker_data.positionId
                logger.info(f"✅ Found position ID: {position_id}")
                
            except Exception as e:
                logger.error(f"❌ Error getting position ID: {e}")
                return
            
            # Place each separate TP order
            for i, tp_leg in enumerate(separate_tp_legs):
                try:
                    logger.info(f"🔧 Processing TP leg {i+1}/{len(separate_tp_legs)}: {tp_leg.kind}")
                    # Calculate quantity based on allocation
                    if hasattr(tp_leg, 'allocation') and tp_leg.allocation and tp_leg.allocation.get("type") == "percentage":
                        quantity_value = order_request.quantity.value * (tp_leg.allocation["value"] / 100.0)
                    else:
                        quantity_value = tp_leg.allocation.get("value", 100.0) if hasattr(tp_leg, 'allocation') and tp_leg.allocation else 100.0
                    
                    # Snap quantity to lot size
                    original_quantity = quantity_value
                    snapped_quantity = broker.snap_to_lot(quantity_value, order_request.instrument.symbol)
                    logger.info(f"🔧 Snapping quantity: {original_quantity} → {snapped_quantity}")
                    
                    # Convert quantity to broker units (contracts)
                    broker_quantity = broker.convert_quantity_to_broker_units(snapped_quantity, order_request.instrument.symbol)
                    logger.info(f"🔧 Converting quantity to broker units: {snapped_quantity} → {broker_quantity}")
                    
                    # Snap TP price to tick size
                    original_tp_price = tp_leg.trigger["value"]
                    logger.info(f"🔧 Snapping TP price: {original_tp_price} for symbol: {order_request.instrument.symbol}")
                    snapped_tp_price = broker.snap_to_tick(original_tp_price, order_request.instrument.symbol)
                    logger.info(f"🔧 Snapped TP price: {original_tp_price} → {snapped_tp_price}")
                    
                    # Create MEXC close order directly (not through COM schema)
                    from mexcpy.mexcTypes import CreateOrderRequest, OrderSide, OrderType, OpenType
                    
                    # Determine close side based on entry side
                    if order_request.side == "BUY":
                        close_side = OrderSide.CloseLong  # Close the long position
                    else:
                        close_side = OrderSide.CloseShort  # Close the short position
                    
                    # TP orders are LIMIT orders (post-only)
                    order_type = OrderType.PostOnlyMaker
                    order_price = snapped_tp_price
                    
                    # Create MEXC close order request
                    mexc_close_order = CreateOrderRequest(
                        symbol=broker._map_symbol_to_mexc(order_request.instrument.symbol),
                        vol=broker_quantity,  # Use the converted broker quantity
                        side=close_side,
                        type=order_type,
                        openType=OpenType.Isolated,
                        price=order_price,
                        leverage=order_request.leverage.leverage if order_request.leverage else 1,
                        positionId=position_id,  # Use the position ID from the filled order
                        reduceOnly=True  # This is a close order
                    )
                    
                    logger.info(f"🔧 Creating MEXC TP close order: {close_side.name} for position {position_id}")
                    
                    # Place the close order directly with MEXC
                    result = await broker.api.create_order(mexc_close_order)
                    
                    if result.success:
                        logger.info(f"✅ Placed TP close order: {result.data.orderId} at {snapped_tp_price} for position {position_id}")
                        
                        # Track the exit order
                        try:
                            from .position_tracker import position_tracker, OrderType
                            from .order_monitor import order_monitor
                            
                            # Find the internal position ID for tracking
                            internal_position_id = None
                            for pos_id, position in position_tracker.positions.items():
                                if position.order_ref == order.order_ref:
                                    internal_position_id = pos_id
                                    break
                            
                            if position_id:
                                tp_order_id = position_tracker.add_order(
                                    broker_order_id=result.data.orderId,
                                    parent_position_id=position_id,
                                    order_type=OrderType.TP,
                                    side=close_side,
                                    quantity=broker_quantity,
                                    price=snapped_tp_price,
                                    strategy_id=order_request.source.strategy_id if hasattr(order_request, 'source') and order_request.source else "unknown",
                                    order_ref=f"{order.order_ref}_tp{i+1}"
                                )
                                logger.info(f"📋 Tracked TP order: {tp_order_id}")
                                
                                # Add post-only TP order to monitoring for cancellation handling
                                try:
                                    # Get the original monitored order for after_fill_actions
                                    original_monitored_order = order_monitor.get_monitored_order(order.order_ref)
                                    
                                    if original_monitored_order:
                                        await order_monitor.add_post_only_tp_for_monitoring(
                                            order_ref=f"{order.order_ref}_tp{i+1}",
                                            symbol=order_request.instrument.symbol,
                                            side=close_side,
                                            quantity=broker_quantity,
                                            price=snapped_tp_price,
                                            position_id=position_id,
                                            original_monitored_order=original_monitored_order
                                        )
                                        logger.info(f"🔍 Added post-only TP order {order.order_ref}_tp{i+1} to monitoring")
                                    else:
                                        logger.warning(f"❌ Original monitored order not found for {order.order_ref}")
                                except Exception as e:
                                    logger.error(f"Error adding TP order to monitoring: {e}")
                                
                                # Log TP order to CSV with broker order ID
                                try:
                                    await self._log_tp_sl_order(
                                        original_request,  # Use original request with source attribute
                                        result.data.orderId,
                                        "TP",
                                        close_side,
                                        broker_quantity,
                                        snapped_tp_price,
                                        order.order_ref
                                    )
                                    logger.info(f"✅ Logged TP order {order.order_ref}_tp with broker ID {result.data.orderId}")
                                except Exception as e:
                                    logger.error(f"Error logging TP order: {e}")
                        
                        except Exception as e:
                            logger.error(f"Error tracking TP order: {e}")
                    else:
                        logger.error(f"❌ Failed to place TP close order: {result.message}")
                        
                except Exception as e:
                    logger.error(f"Error placing TP order: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
        
        except Exception as e:
            logger.error(f"Error in _handle_post_only_tp_immediately: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _log_attached_tp_sl_orders(self, order_request, order, broker_order_id, original_request=None):
        """Log attached TP/SL orders to CSV (non-post-only legs that are attached to main order by MEXC)"""
        try:
            if not order_request.exit_plan or not order_request.exit_plan.legs:
                return
            
            # Find TP/SL legs that should be logged as separate orders
            # TPs are post-only LIMIT orders (separate orders)
            # SLs are MARKET orders (attached to main order by MEXC)
            separate_orders = []
            attached_legs = []
            
            for leg in (order_request.exit_plan.legs or []):
                if leg.kind in ["TP", "SL"] and hasattr(leg, 'exec') and leg.exec:
                    exec_config = leg.exec
                    is_post_only = False
                    if isinstance(exec_config, dict) and exec_config.get('post_only'):
                        is_post_only = True
                    elif hasattr(exec_config, 'post_only') and exec_config.post_only:
                        is_post_only = True
                    
                    # TPs are post-only LIMIT orders - these are separate orders
                    if leg.kind == "TP" and is_post_only:
                        separate_orders.append(leg)
                    # SLs are MARKET orders - these are attached to main order by MEXC
                    elif leg.kind == "SL" and not is_post_only:
                        attached_legs.append(leg)
            
            # Log separate TP orders (post-only LIMIT orders)
            if separate_orders:
                logger.info(f"🚀 Logging {len(separate_orders)} separate TP orders for order {order.order_ref}")
                for i, leg in enumerate(separate_orders):
                    try:
                        # Create separate TP order entry
                        tp_order_data = {
                            'timestamp': datetime.utcnow().isoformat(),
                            'order_id': f"{order.order_ref}_tp{i+1}",
                            'strategy_id': order.strategy_id,
                            'account_id': order.account_id,
                            'symbol': order.symbol,
                            'side': 'SELL' if order.side == 'BUY' else 'BUY',  # Opposite side for TP
                            'order_type': 'TP',
                            'quantity': leg.allocation.value if hasattr(leg.allocation, 'value') else 100.0,
                            'price': leg.exec.price if hasattr(leg.exec, 'price') else 0.0,
                            'stop_price': None,
                            'time_in_force': leg.exec.time_in_force if hasattr(leg.exec, 'time_in_force') else 'GTC',
                            'status': 'OPEN',
                            'broker': 'mexc',
                            'broker_order_id': '',  # Will be filled when order is placed
                            'position_id': order.position_id,
                            'leverage': order.leverage,
                            'volume': 0.0,
                            'commission': 0.0,
                            'fill_price': None,
                            'fill_quantity': None,
                            'fill_time': None
                        }
                        
                        await data_logger.log_order(tp_order_data)
                        logger.info(f"📊 Logged TP order: {tp_order_data['order_id']} as OPEN")
                        logger.info(f"✅ Logged separate TP order: {tp_order_data['order_id']} at {tp_order_data['price']}")
                        
                    except Exception as e:
                        logger.error(f"❌ Error logging separate TP order: {e}")
            
            # Log attached SL orders (MARKET orders attached to main order by MEXC)
            if not attached_legs:
                logger.info(f"No attached SL legs to log for order {order.order_ref}")
                return
            
            # Validate: Only one SL should be attached per position
            if len(attached_legs) > 1:
                logger.warning(f"⚠️ Multiple SL legs detected ({len(attached_legs)}), only logging the first one")
                attached_legs = [attached_legs[0]]  # Only keep the first SL
            
            logger.info(f"🚀 Logging {len(attached_legs)} attached SL orders for order {order.order_ref}")
            
            # Log each attached SL leg (should only be one SL per position)
            for i, leg in enumerate(attached_legs):
                try:
                    # Extract price from leg
                    leg_price = None
                    if hasattr(leg, 'trigger') and hasattr(leg.trigger, 'value'):
                        leg_price = leg.trigger.value
                    elif hasattr(leg, 'trigger') and isinstance(leg.trigger, dict):
                        leg_price = leg.trigger.get('value')
                    
                    if leg_price is None:
                        logger.warning(f"Could not extract price for {leg.kind} leg")
                        continue
                    
                    # Determine side for TP/SL order
                    if leg.kind == "TP":
                        # TP: opposite side of entry order
                        tp_sl_side = "SELL" if order_request.side == "BUY" else "BUY"
                    else:  # SL
                        # SL: opposite side of entry order  
                        tp_sl_side = "SELL" if order_request.side == "BUY" else "BUY"
                    
                    # Calculate quantity based on allocation
                    if hasattr(leg, 'allocation') and leg.allocation and leg.allocation.get("type") == "percentage":
                        quantity_value = order_request.quantity.value * (leg.allocation.get("value", 100.0) / 100.0)
                    else:
                        quantity_value = leg.allocation.get("value", 100.0) if hasattr(leg, 'allocation') and leg.allocation else 100.0
                    
                    # Log the attached TP/SL order to CSV
                    await self._log_tp_sl_order(
                        original_request,
                        "",  # No broker order ID for attached orders (they're part of main order)
                        leg.kind,
                        tp_sl_side,
                        quantity_value,
                        leg_price,
                        order.order_ref
                    )
                    
                    sl_order_id = f"{order.order_ref}_sl{i+1}" if i > 0 else f"{order.order_ref}_sl"
                    logger.info(f"✅ Logged attached {leg.kind} order: {sl_order_id} at {leg_price}")
                    

                    
                except Exception as e:
                    logger.error(f"Error logging attached {leg.kind} order: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
        
        except Exception as e:
            logger.error(f"Error in _log_attached_tp_sl_orders: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _send_gui_order_event(self, order, event_type: str):
        """Send order event to GUI subscribers"""
        try:
            from ..ws.hub import websocket_hub
            from ..schemas.base import WSEvent, EventType
            from datetime import datetime
            
            # Create GUI event data
            gui_event_data = {
                "order_id": order.order_ref,
                "symbol": getattr(order, 'symbol', 'UNKNOWN') if hasattr(order, 'symbol') else (order.instrument.symbol if hasattr(order, 'instrument') and order.instrument else 'UNKNOWN'),
                "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                "quantity": order.quantity if hasattr(order, 'quantity') and order.quantity else 0.0,
                "price": order.price if hasattr(order, 'price') else 0.0,
                "broker": "mexc",  # Default broker
                "status": "QUEUED",
                "timestamp": datetime.utcnow().isoformat(),
                "strategy_id": order.source.strategy_id if hasattr(order, 'source') and order.source else "unknown"
            }
            
            # Create WebSocket event
            event = WSEvent(
                event_type=EventType.ORDER_UPDATE,
                occurred_at=datetime.utcnow(),
                order_ref=order.order_ref,
                details=gui_event_data
            )
            
            # Broadcast to GUI subscribers
            await websocket_hub.broadcast_event("GUI", event)
            logger.info(f"📡 Sent GUI event: {event_type} for order {order.order_ref}")
            
        except Exception as e:
            logger.error(f"Error sending GUI event: {e}")
    
    async def _log_order_data(self, request, broker_result, order_ref: str):
        """Log order data to comprehensive logging system"""
        try:
            from .data_logger import data_logger
            
            # Get symbol from order object
            symbol = request.order.instrument.symbol
            
            # Get side from order object
            if hasattr(request.order.side, 'value'):
                side = request.order.side.value
            else:
                side = str(request.order.side)
            
            # Get order type from order object
            if hasattr(request.order.order_type, 'value'):
                order_type = request.order.order_type.value
            else:
                order_type = str(request.order.order_type)
            
            # Get quantity from order object
            if hasattr(request.order.quantity, 'value'):
                quantity = request.order.quantity.value
            else:
                quantity = float(request.order.quantity)
            
            # Get leverage from order object
            if hasattr(request.order.leverage, 'leverage'):
                leverage = request.order.leverage.leverage
            else:
                leverage = float(request.order.leverage)
            
            order_data = {
                'order_id': order_ref,  # Use the generated order_ref
                'strategy_id': request.source.strategy_id,
                'account_id': request.source.instance_id,
                'symbol': symbol,
                'side': side,
                'order_type': order_type,
                'quantity': quantity,
                'price': request.order.price or 0.0,
                'stop_price': request.order.stop_price,
                'time_in_force': request.order.time_in_force,
                'status': "OPEN" if broker_result["success"] else "REJECTED",
                'broker': "mexc",
                'broker_order_id': broker_result.get("broker_order_id", ""),
                'position_id': "",
                'leverage': leverage,
                'margin_used': 0.0,
                'commission': 0.0,
                'fill_price': None,
                'fill_quantity': None,
                'fill_time': None,
                'pnl': None,
                'exit_reason': None
            }
            
            await data_logger.log_order(order_data)
            
        except Exception as e:
            logger.error(f"❌ Error logging order data: {e}")
    
    async def update_order_fill_data(self, broker_order_id: str):
        """Update order log with fill information from broker"""
        try:
            from .data_logger import data_logger
            from ..adapters.manager import broker_manager
            
            # Get MEXC adapter
            broker = broker_manager.get_adapter("mexc")
            if not broker:
                logger.error("❌ MEXC broker adapter not found")
                return
            
            # Get order details from broker
            order_result = await broker.get_order(broker_order_id)
            if not order_result:
                logger.warning(f"⚠️ Could not fetch order details for {broker_order_id}")
                return
            
            # Extract fill information
            broker_data = order_result.get("broker_data")
            if not broker_data:
                logger.warning(f"⚠️ No broker data for order {broker_order_id}")
                return
            
            # Get fill details from order
            fill_price = getattr(broker_data, 'dealAvgPrice', None)
            fill_quantity = getattr(broker_data, 'dealVol', None)
            commission = (getattr(broker_data, 'takerFee', 0.0) + 
                         getattr(broker_data, 'makerFee', 0.0))
            pnl = getattr(broker_data, 'profit', None)
            
            # Get detailed transaction history for more accurate fill time
            try:
                transactions_result = await broker.api.get_order_transactions(broker_order_id)
                if transactions_result.success and transactions_result.data:
                    # Use the latest transaction timestamp as fill time
                    latest_transaction = max(transactions_result.data, key=lambda t: t.get('timestamp', 0))
                    fill_time = datetime.fromtimestamp(latest_transaction.get('timestamp', 0) / 1000)
                else:
                    # Fallback to order update time
                    fill_time = datetime.fromtimestamp(broker_data.updateTime / 1000) if hasattr(broker_data, 'updateTime') else None
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch transaction details: {e}")
                fill_time = datetime.fromtimestamp(broker_data.updateTime / 1000) if hasattr(broker_data, 'updateTime') else None
            
            # Update order log with fill information
            fill_data = {
                'broker_order_id': broker_order_id,
                'fill_price': fill_price,
                'fill_quantity': fill_quantity,
                'fill_time': fill_time,
                'commission': commission
            }
            
            await data_logger.update_order_fill(fill_data)

            # Also update the order status to FILLED if we have fill data
            if fill_price and fill_quantity:
                # Find the internal order ID that matches this broker order ID
                internal_order_id = None
                try:
                    from .data_logger import data_logger
                    # Read CSV to find the internal order ID
                    if data_logger.main_orders_csv.exists():
                        with open(data_logger.main_orders_csv, 'r', newline='') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('broker_order_id') == broker_order_id:
                                    internal_order_id = row.get('order_id')
                                    break
                except Exception as e:
                    logger.warning(f"Could not find internal order ID for broker order {broker_order_id}: {e}")
                
                if internal_order_id:
                    await self.update_order_status(internal_order_id, "FILLED", {
                        'price': fill_price,
                        'quantity': fill_quantity,
                        'time': fill_time,
                        'commission': commission
                    })
                    logger.info(f"✅ Updated order {internal_order_id} (broker: {broker_order_id}) status to FILLED with fill data")
                else:
                    logger.warning(f"Could not find internal order ID for broker order {broker_order_id}")
            else:
                logger.info(f"✅ Updated fill data for order {broker_order_id}: price={fill_price}, qty={fill_quantity}, commission={commission}")
            
        except Exception as e:
            logger.error(f"❌ Error updating order fill data: {e}")
    
    async def _log_tp_sl_order(self, request, broker_order_id: str, order_type: str, side, quantity: float, price: float, parent_order_ref: str):
        """Log TP/SL orders to CSV"""
        try:
            from .data_logger import data_logger
            
            # Get side string
            if hasattr(side, 'name'):
                side_str = side.name
            else:
                side_str = str(side)
            
            # Handle different request types
            if hasattr(request, 'source'):
                # CreateOrderRequest with source
                strategy_id = request.source.strategy_id
                account_id = request.source.instance_id
                symbol = request.order.instrument.symbol
                leverage = request.order.leverage.leverage if request.order.leverage else 1.0
            else:
                # OrderRequest without source - try to get from parent order
                strategy_id = "unknown"
                account_id = "unknown"
                symbol = "unknown"
                leverage = 1.0
                
                # Try to extract from parent order ref if it contains strategy info
                if "_" in parent_order_ref:
                    parts = parent_order_ref.split("_")
                    if len(parts) >= 2:
                        strategy_id = parts[0]
                        account_id = parts[1] if len(parts) > 1 else "unknown"
            
            order_data = {
                'order_id': f"{parent_order_ref}_{order_type.lower()}",
                'strategy_id': strategy_id,
                'account_id': account_id,
                'symbol': symbol,
                'side': side_str,
                'order_type': order_type,
                'quantity': quantity,
                'price': price,
                'stop_price': None,
                'time_in_force': "GTC",
                'status': "OPEN",  # Start as OPEN
                'broker': "mexc",
                'broker_order_id': broker_order_id,
                'position_id': "",
                'leverage': leverage,
                'margin_used': 0.0,
                'commission': 0.0,
                'fill_price': None,
                'fill_quantity': None,
                'fill_time': None
            }
            
            await data_logger.log_order(order_data)
            logger.info(f"📊 Logged {order_type} order: {order_data['order_id']} as OPEN")
            
        except Exception as e:
            logger.error(f"❌ Error logging {order_type} order: {e}")
    
    async def update_order_status(self, order_id: str, new_status: str, fill_data: dict = None):
        """Update order status in CSV logs"""
        try:
            from .data_logger import data_logger
            from .position_tracker import position_tracker
            from .order_monitor import order_monitor
            
            update_data = {
                'status': new_status
            }
            
            # Add fill data if provided
            if fill_data:
                update_data.update({
                    'fill_price': fill_data.get('price'),
                    'fill_quantity': fill_data.get('quantity'),
                    'fill_time': fill_data.get('time'),
                    'commission': fill_data.get('commission')
                })
                
                # If this is a FILLED status with fill data, try to update position entry price
                if new_status == "FILLED" and fill_data.get('price'):
                    try:
                        # Find the position that has this order
                        for position_id, position in position_tracker.positions.items():
                            if position.order_ref == order_id:
                                # Only update position entry price if it's not already set or different
                                if position.entry_price != fill_data.get('price'):
                                    # Update position entry price
                                    position_tracker.update_position(position_id, entry_price=fill_data.get('price'))
                                    logger.info(f"📊 Updated position {position_id} entry price to {fill_data.get('price')} from order {order_id}")
                                    
                                    # Also update the position tracker's entry order status
                                    for order_tracker_id, order_tracker in position_tracker.orders.items():
                                        if (order_tracker.parent_position_id == position_id and 
                                            order_tracker.order_type == OrderType.ENTRY and 
                                            order_tracker.order_ref == order_id):
                                            position_tracker.update_order_status(
                                                order_tracker_id, 
                                                OrderStatus.FILLED, 
                                                fill_data.get('quantity', 0.0), 
                                                fill_data.get('price', 0.0)
                                            )
                                            logger.info(f"📊 Updated position tracker entry order {order_tracker_id} status to FILLED")
                                            break
                                else:
                                    logger.info(f"📊 Position {position_id} entry price already set to {fill_data.get('price')}, skipping update")
                                break
                    except Exception as e:
                        logger.warning(f"Could not update position entry price for order {order_id}: {e}")
            
            # Handle post-only order cancellations
            if new_status == "CANCELLED":
                await self._handle_post_only_cancellation(order_id)
            
            await data_logger.update_order(order_id, update_data)
            logger.info(f"📊 Updated order {order_id} status to {new_status}")
            
        except Exception as e:
            logger.error(f"❌ Error updating order status: {e}")
    
    async def _handle_post_only_cancellation(self, order_id: str):
        """Handle when any post-only order is cancelled (crossed the books)"""
        try:
            from .order_monitor import order_monitor
            
            logger.info(f"🔄 Checking if cancelled order {order_id} was a post-only order")
            
            # Check if this order is being monitored as a post-only order
            if order_monitor.is_monitoring(order_id):
                monitored_order = order_monitor.get_monitored_order(order_id)
                
                if monitored_order and monitored_order.status.startswith("MONITORING_POST_ONLY_"):
                    logger.info(f"🔄 Post-only order {order_id} was cancelled - executing market order")
                    await order_monitor.handle_post_only_cancellation(order_id)
                else:
                    logger.info(f"ℹ️ Order {order_id} is monitored but not a post-only order")
            else:
                logger.info(f"ℹ️ Order {order_id} is not being monitored")
                
        except Exception as e:
            logger.error(f"Error handling post-only cancellation: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def get_order_by_ref(self, order_ref: str) -> dict:
        """Get order data by order reference from CSV"""
        try:
            from .data_logger import data_logger
            order_data = await data_logger.get_order_by_ref(order_ref)
            return order_data
        except Exception as e:
            logger.error(f"Error getting order by ref {order_ref}: {e}")
            return None

    async def cleanup_position_orders(self, order_ref: str, reason: str = "POSITION_CLOSED"):
        """Clean up all orders associated with a position when it's closed"""
        try:
            from .order_monitor import order_monitor
            await order_monitor.cleanup_position_orders(order_ref, reason)
            logger.info(f"Position cleanup initiated for {order_ref}: {reason}")
        except Exception as e:
            logger.error(f"Error initiating position cleanup for {order_ref}: {e}")

# Global order service instance
order_service = OrderService()
