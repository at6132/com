"""
Main API router for v1 endpoints
Includes all domain routers
"""
from fastapi import APIRouter

from .orders import router as orders_router
from .positions import router as positions_router
from .balances import router as balances_router
from .events import router as events_router
from .websocket import router as websocket_router

# Main v1 API router
api_router = APIRouter()

# Include domain routers
api_router.include_router(orders_router, prefix="/orders", tags=["orders"])
api_router.include_router(positions_router, prefix="/positions", tags=["positions"])
api_router.include_router(balances_router, prefix="/balances", tags=["balances"])
api_router.include_router(events_router, prefix="/events", tags=["events"])
api_router.include_router(websocket_router, tags=["websocket"])
