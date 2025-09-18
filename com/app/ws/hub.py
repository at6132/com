"""
WebSocket hub for COM backend
Real-time event streaming with authentication and subscriptions
"""
import json
import logging
import asyncio
import time
from typing import Dict, Set, Optional, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..schemas.events import (
    WSAuthMessage, WSSubscribeMessage, WSUnsubscribeMessage, WSPingMessage,
    WSAuthResponse, WSSubscribeResponse, WSPongResponse
)
from ..schemas.base import WSEvent
from ..security.auth import verify_websocket_hmac_signature
from ..core.database import get_db, ApiKey

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections and subscriptions"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # connection_id -> WebSocket
        self.subscriptions: Dict[str, Set[str]] = {}  # strategy_id -> set of connection_ids
        self.authenticated_connections: Set[str] = set()  # Set of authenticated connection IDs
        self.connection_strategies: Dict[str, Set[str]] = {}  # connection_id -> set of strategy_ids
        self.connection_last_ping: Dict[str, float] = {}  # connection_id -> last ping time
        self.connection_last_pong: Dict[str, float] = {}  # connection_id -> last pong time
        self.heartbeat_interval = 30  # Send heartbeat every 30 seconds
        self.heartbeat_timeout = 60  # Consider connection dead after 60 seconds without pong
        self.heartbeat_task: Optional[asyncio.Task] = None
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.connection_strategies[connection_id] = set()
        current_time = time.time()
        self.connection_last_ping[connection_id] = current_time
        self.connection_last_pong[connection_id] = current_time
        logger.info(f"WebSocket connection {connection_id} established")
        
        # Start heartbeat task if not already running
        if not self.heartbeat_task or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    def disconnect(self, connection_id: str):
        """Remove a WebSocket connection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Remove from subscriptions
        if connection_id in self.connection_strategies:
            strategies = self.connection_strategies[connection_id]
            for strategy_id in strategies:
                if strategy_id in self.subscriptions:
                    self.subscriptions[strategy_id].discard(connection_id)
                    if not self.subscriptions[strategy_id]:
                        del self.subscriptions[strategy_id]
            del self.connection_strategies[connection_id]
        
        # Remove from authenticated set
        self.authenticated_connections.discard(connection_id)
        
        # Remove heartbeat tracking
        if connection_id in self.connection_last_ping:
            del self.connection_last_ping[connection_id]
        if connection_id in self.connection_last_pong:
            del self.connection_last_pong[connection_id]
        
        logger.info(f"WebSocket connection {connection_id} disconnected")
    
    async def authenticate(self, connection_id: str, auth_message: WSAuthMessage) -> WSAuthResponse:
        """Authenticate a WebSocket connection using HMAC"""
        try:
            logger.info(f"Authenticating WebSocket connection {connection_id}")
            logger.info(f"Auth message: key_id={auth_message.key_id}, ts={auth_message.ts}, signature={auth_message.signature[:20]}...")
            
            # Get database session using the same pattern as REST API
            from ..core.database import get_async_session_local
            logger.info(f"Getting database session maker...")
            session_maker = get_async_session_local()
            logger.info(f"Session maker created: {session_maker}")
            
            async with session_maker() as db:
                logger.info(f"Database session acquired: {db}")
                
                # Test basic database connectivity
                try:
                    from sqlalchemy import text
                    result = await db.execute(text("SELECT 1"))
                    logger.info(f"Database connectivity test successful")
                except Exception as e:
                    logger.error(f"Database connectivity test failed: {e}")
                    return WSAuthResponse(status="AUTH_NACK", message="Database connection failed")
                
                # Find API key using explicit query instead of db.get()
                logger.info(f"Looking for API key: {auth_message.key_id}")
                try:
                    from sqlalchemy import select
                    result = await db.execute(
                        select(ApiKey).where(ApiKey.key_id == auth_message.key_id)
                    )
                    api_key = result.scalar_one_or_none()
                    
                    if not api_key:
                        logger.warning(f"API key not found: {auth_message.key_id}")
                        
                        # Let's check what API keys do exist
                        try:
                            result = await db.execute(select(ApiKey))
                            api_keys = result.scalars().all()
                            logger.info(f"Found {len(api_keys)} API keys in database:")
                            for key in api_keys:
                                logger.info(f"  - {key.key_id} (active: {key.is_active})")
                        except Exception as e:
                            logger.error(f"Error querying API keys: {e}")
                        
                        return WSAuthResponse(status="AUTH_NACK", message="Invalid API key")
                        
                except Exception as e:
                    logger.error(f"Error executing API key query: {e}")
                    return WSAuthResponse(status="AUTH_NACK", message="Database query error")
                
                logger.info(f"API key found: {api_key.key_id}, secret_key length: {len(api_key.secret_key) if api_key.secret_key else 'None'}")
                
                # Verify HMAC signature
                auth_data = {
                    "key_id": auth_message.key_id,
                    "ts": auth_message.ts
                }
                
                logger.info(f"Calling verify_websocket_hmac_signature with:")
                logger.info(f"  secret_key: {api_key.secret_key[:20] if api_key.secret_key else 'None'}...")
                logger.info(f"  signature: {auth_message.signature}")
                logger.info(f"  timestamp: {auth_message.ts}")
                logger.info(f"  auth_data: {auth_data}")
                
                is_valid = verify_websocket_hmac_signature(
                    api_key.secret_key,
                    auth_message.signature,
                    auth_message.ts,
                    auth_data
                )
                
                logger.info(f"HMAC verification result: {is_valid}")
                
                if not is_valid:
                    logger.warning(f"Invalid HMAC signature for connection {connection_id}")
                    return WSAuthResponse(status="AUTH_NACK", message="Invalid signature")
                
                # Authentication successful
                self.authenticated_connections.add(connection_id)
                logger.info(f"WebSocket connection {connection_id} authenticated successfully")
                return WSAuthResponse(status="AUTH_ACK")
                
        except Exception as e:
            logger.error(f"Authentication error for connection {connection_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return WSAuthResponse(status="AUTH_NACK", message="Authentication failed")
    
    async def subscribe(self, connection_id: str, subscribe_message: WSSubscribeMessage) -> WSSubscribeResponse:
        """Subscribe to strategy events or GUI data feed"""
        if connection_id not in self.authenticated_connections:
            return WSSubscribeResponse(status="UNSUBSCRIBED", strategy_id=subscribe_message.strategy_id, message="Not authenticated")
        
        strategy_id = subscribe_message.strategy_id
        
        # Special handling for GUI subscription
        if strategy_id.upper() == "GUI":
            strategy_id = "GUI"  # Normalize to uppercase
            
        # Add to subscriptions
        if strategy_id not in self.subscriptions:
            self.subscriptions[strategy_id] = set()
        self.subscriptions[strategy_id].add(connection_id)
        
        # Add to connection strategies
        self.connection_strategies[connection_id].add(strategy_id)
        
        logger.info(f"Connection {connection_id} subscribed to {strategy_id}")
        return WSSubscribeResponse(status="SUBSCRIBED", strategy_id=strategy_id)
    
    async def unsubscribe(self, connection_id: str, unsubscribe_message: WSUnsubscribeMessage) -> WSSubscribeResponse:
        """Unsubscribe from strategy events"""
        strategy_id = unsubscribe_message.strategy_id
        
        # Remove from subscriptions
        if strategy_id in self.subscriptions:
            self.subscriptions[strategy_id].discard(connection_id)
            if not self.subscriptions[strategy_id]:
                del self.subscriptions[strategy_id]
        
        # Remove from connection strategies
        if connection_id in self.connection_strategies:
            self.connection_strategies[connection_id].discard(strategy_id)
        
        logger.info(f"Connection {connection_id} unsubscribed from strategy {strategy_id}")
        return WSSubscribeResponse(status="UNSUBSCRIBED", strategy_id=strategy_id)
    
    async def send_pong(self, connection_id: str, ping_message: WSPingMessage):
        """Send pong response to ping"""
        if connection_id in self.active_connections:
            pong_response = WSPongResponse(ts=ping_message.ts)
            await self.active_connections[connection_id].send_text(pong_response.model_dump_json())
            # Update last pong time
            self.connection_last_pong[connection_id] = time.time()
    
    async def broadcast_event(self, strategy_id: str, event: WSEvent):
        """Broadcast event to all subscribers of a strategy"""
        if strategy_id not in self.subscriptions:
            return
        
        event_json = event.model_dump_json()
        disconnected_connections = []
        
        for connection_id in self.subscriptions[strategy_id]:
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(event_json)
                except Exception as e:
                    logger.error(f"Failed to send event to {connection_id}: {e}")
                    disconnected_connections.append(connection_id)
            else:
                disconnected_connections.append(connection_id)
        
        # Clean up disconnected connections
        for connection_id in disconnected_connections:
            self.disconnect(connection_id)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats and check connection health"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                current_time = time.time()
                dead_connections = []
                
                # Check all authenticated connections
                for connection_id in list(self.authenticated_connections):
                    if connection_id not in self.active_connections:
                        dead_connections.append(connection_id)
                        continue
                    
                    # Check if connection is still alive
                    last_pong = self.connection_last_pong.get(connection_id, 0)
                    if current_time - last_pong > self.heartbeat_timeout:
                        logger.warning(f"Connection {connection_id} timed out (no pong for {current_time - last_pong:.1f}s)")
                        dead_connections.append(connection_id)
                        continue
                    
                    # Send heartbeat to this connection
                    try:
                        heartbeat_event = WSEvent(
                            event_type="HEARTBEAT",
                            occurred_at=datetime.utcnow(),
                            order_ref="heartbeat",
                            details={"timestamp": current_time}
                        )
                        await self.active_connections[connection_id].send_text(heartbeat_event.model_dump_json())
                        logger.debug(f"Sent heartbeat to {connection_id}")
                    except Exception as e:
                        logger.error(f"Failed to send heartbeat to {connection_id}: {e}")
                        dead_connections.append(connection_id)
                
                # Clean up dead connections
                for connection_id in dead_connections:
                    logger.info(f"Removing dead connection {connection_id}")
                    self.disconnect(connection_id)
                
                # Stop heartbeat loop if no connections
                if not self.authenticated_connections:
                    logger.info("No active connections, stopping heartbeat loop")
                    break
                    
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

class WebSocketHub:
    """Main WebSocket hub for handling connections and messages"""
    
    def __init__(self):
        self.connection_manager = ConnectionManager()
    
    async def handle_websocket(self, websocket: WebSocket):
        """Handle a WebSocket connection"""
        connection_id = f"conn_{id(websocket)}"
        
        try:
            await self.connection_manager.connect(websocket, connection_id)
            
            while True:
                # Receive message
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                    message_type = message_data.get("type")
                    
                    if message_type == "AUTH":
                        auth_message = WSAuthMessage(**message_data)
                        response = await self.connection_manager.authenticate(connection_id, auth_message)
                        await websocket.send_text(response.model_dump_json())
                    
                    elif message_type == "SUBSCRIBE":
                        subscribe_message = WSSubscribeMessage(**message_data)
                        response = await self.connection_manager.subscribe(connection_id, subscribe_message)
                        await websocket.send_text(response.model_dump_json())
                    
                    elif message_type == "UNSUBSCRIBE":
                        unsubscribe_message = WSUnsubscribeMessage(**message_data)
                        response = await self.connection_manager.unsubscribe(connection_id, unsubscribe_message)
                        await websocket.send_text(response.model_dump_json())
                    
                    elif message_type == "PING":
                        ping_message = WSPingMessage(**message_data)
                        await self.connection_manager.send_pong(connection_id, ping_message)
                    
                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                        await websocket.send_text(json.dumps({
                            "error": "Unknown message type",
                            "type": message_type
                        }))
                
                except ValidationError as e:
                    logger.error(f"Invalid message format: {e}")
                    await websocket.send_text(json.dumps({
                        "error": "Invalid message format",
                        "details": str(e)
                    }))
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_text(json.dumps({
                        "error": "Internal error",
                        "details": str(e)
                    }))
        
        except WebSocketDisconnect:
            logger.info(f"WebSocket {connection_id} disconnected")
        except Exception as e:
            logger.error(f"WebSocket {connection_id} error: {e}")
        finally:
            self.connection_manager.disconnect(connection_id)
    
    async def broadcast_event(self, strategy_id: str, event: WSEvent):
        """Broadcast an event to all subscribers"""
        await self.connection_manager.broadcast_event(strategy_id, event)

# Global WebSocket hub instance
websocket_hub = WebSocketHub()
