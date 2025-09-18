"""
WebSocket endpoint for real-time event streaming
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ...ws.hub import websocket_hub

router = APIRouter()

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming"""
    await websocket_hub.handle_websocket(websocket)
