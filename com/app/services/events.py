"""
Events service for broadcasting events via WebSocket
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from ..schemas.events import WSEvent, EventType
from ..ws.hub import websocket_hub

logger = logging.getLogger(__name__)

class EventService:
    """Service for managing and broadcasting events"""
    
    @staticmethod
    async def broadcast_order_update(
        strategy_id: str,
        order_ref: str,
        state: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast order update event"""
        event = WSEvent(
            event_type=EventType.ORDER_UPDATE,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref,
            state=state,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted ORDER_UPDATE for order {order_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_fill(
        strategy_id: str,
        order_ref: str,
        position_ref: Optional[str] = None,
        sub_order_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast fill event"""
        event = WSEvent(
            event_type=EventType.FILL,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref,
            position_ref=position_ref,
            sub_order_ref=sub_order_ref,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted FILL for order {order_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_cancelled(
        strategy_id: str,
        order_ref: str,
        position_ref: Optional[str] = None,
        sub_order_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast cancelled event"""
        event = WSEvent(
            event_type=EventType.CANCELLED,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref,
            position_ref=position_ref,
            sub_order_ref=sub_order_ref,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted CANCELLED for order {order_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_stop_triggered(
        strategy_id: str,
        order_ref: str,
        position_ref: Optional[str] = None,
        sub_order_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast stop loss triggered event"""
        event = WSEvent(
            event_type=EventType.STOP_TRIGGERED,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref,
            position_ref=position_ref,
            sub_order_ref=sub_order_ref,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted STOP_TRIGGERED for order {order_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_take_profit_triggered(
        strategy_id: str,
        order_ref: str,
        position_ref: Optional[str] = None,
        sub_order_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast take profit triggered event"""
        event = WSEvent(
            event_type=EventType.TAKE_PROFIT_TRIGGERED,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref,
            position_ref=position_ref,
            sub_order_ref=sub_order_ref,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted TAKE_PROFIT_TRIGGERED for order {order_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_position_closed(
        strategy_id: str,
        position_ref: str,
        order_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Broadcast position closed event"""
        event = WSEvent(
            event_type=EventType.POSITION_CLOSED,
            occurred_at=datetime.utcnow(),
            order_ref=order_ref or "position_close",
            position_ref=position_ref,
            details=details
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.info(f"Broadcasted POSITION_CLOSED for position {position_ref} to strategy {strategy_id} and GUI")
    
    @staticmethod
    async def broadcast_heartbeat(strategy_id: str):
        """Broadcast heartbeat event"""
        event = WSEvent(
            event_type=EventType.HEARTBEAT,
            occurred_at=datetime.utcnow(),
            order_ref="heartbeat",
            details={"timestamp": datetime.utcnow().isoformat()}
        )
        
        await websocket_hub.broadcast_event(strategy_id, event)
        # Also broadcast to GUI subscribers
        await websocket_hub.broadcast_event("GUI", event)
        logger.debug(f"Broadcasted HEARTBEAT to strategy {strategy_id} and GUI")
