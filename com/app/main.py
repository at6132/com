"""
Main FastAPI application for COM backend
"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import get_settings
from .core.logging import setup_logging
from .core.database import init_db, close_db
from .core.redis import init_redis, close_redis
from .adapters.manager import broker_manager
from .api.v1.router import api_router
from .api.v1.websocket import router as websocket_router

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# ============================================================================
# LIFESPAN EVENTS
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting COM backend...")
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")
        
        # Initialize Redis
        logger.info("Initializing Redis...")
        await init_redis()
        logger.info("Redis initialized successfully")
        
        # Initialize broker manager (lazy initialization - don't connect yet)
        logger.info("Initializing broker manager...")
        await broker_manager.initialize_lazy()
        logger.info("Broker manager initialized successfully")
        
        # Initialize MEXC market data service for COM internal operations
        logger.info("Initializing MEXC market data service for COM internal use...")
        from .services.mexc_market_data import mexc_market_data
        await mexc_market_data.connect()
        
        # Market data service is now symbol-specific - only subscribes when needed
        # by order monitor or position tracker for specific trading pairs
        logger.info("Market data service ready - will subscribe to symbols as needed")
        
        # Initialize order monitoring service for unsupported order types
        logger.info("Initializing order monitoring service...")
        from .services.order_monitor import order_monitor
        await order_monitor.start_monitoring()
        logger.info("Order monitoring service started")
        
        # Start position tracking service
        from .services.position_tracker import position_tracker
        await position_tracker.start_tracking()
        logger.info("Position tracking service started")
        

        
        # Initialize comprehensive data logging system
        from .services.data_logger import data_logger
        await data_logger.initialize_redis()
        logger.info("Data logging system initialized")
        
        # Start balance and performance tracking service
        from .services.balance_tracker import balance_tracker
        await balance_tracker.start_tracking()
        logger.info("Balance tracking service started")
        
        logger.info("COM backend started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start COM backend: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down COM backend...")
    
    try:
        # Shutdown broker manager
        logger.info("Shutting down broker manager...")
        await broker_manager.shutdown()
        logger.info("Broker manager shut down successfully")
        
        # Shutdown order monitoring service
        logger.info("Shutting down order monitoring service...")
        from .services.order_monitor import order_monitor
        await order_monitor.stop_monitoring()
        logger.info("Order monitoring service shut down successfully")
        
        # Stop position tracking service
        from .services.position_tracker import position_tracker
        await position_tracker.stop_tracking()
        logger.info("Position tracking service stopped")
        
        # Shutdown MEXC market data service
        logger.info("Shutting down MEXC market data service...")
        from .services.mexc_market_data import mexc_market_data
        await mexc_market_data.disconnect()
        logger.info("MEXC market data service shut down successfully")
        
        # Close Redis
        logger.info("Closing Redis connections...")
        await close_redis()
        logger.info("Redis connections closed")
        
        # Close database
        logger.info("Closing database connections...")
        await close_db()
        logger.info("Database connections closed")
        
        logger.info("COM backend shut down successfully")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Central Order Manager (COM)",
    description="High-frequency trading order routing and risk management backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# GLOBAL EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail,
                "status_code": exc.status_code
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": str(exc) if settings.debug else None
            }
        }
    )

# ============================================================================
# HEALTH & READINESS ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint - optimized for speed, no external calls"""
    return {"status": "healthy", "service": "COM Backend"}

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint - optimized for speed"""
    try:
        # Quick checks only - no heavy operations
        return {"status": "ready", "service": "COM Backend"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@app.get("/brokers/health")
async def broker_health_check():
    """Broker health check endpoint - with lazy connection"""
    try:
        health_status = {}
        for name, broker in broker_manager.get_enabled_brokers().items():
            try:
                # Lazy connect if not already connected
                if name not in broker_manager.adapters:
                    await broker_manager.ensure_broker_connected(name)
                
                adapter = broker_manager.get_adapter(name)
                if adapter:
                    is_healthy = await adapter.health_check()
                    health_status[name] = {
                        "enabled": broker.enabled,
                        "healthy": is_healthy,
                        "environment": broker.environment
                    }
                else:
                    health_status[name] = {
                        "enabled": broker.enabled,
                        "healthy": False,
                        "error": "Adapter not available"
                    }
            except Exception as e:
                health_status[name] = {
                    "enabled": broker.enabled,
                    "healthy": False,
                    "error": str(e)
                }
        
        return {
            "status": "broker_health_check",
            "brokers": health_status
        }
    except Exception as e:
        logger.error(f"Broker health check failed: {e}")
        raise HTTPException(status_code=500, detail="Broker health check failed")

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Central Order Manager (COM)",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "brokers_health": "/brokers/health",
            "api_docs": "/docs",
            "api_v1": "/api/v1",
            "websocket": "/api/v1/stream"
        },
        "description": "High-frequency trading order routing and risk management backend"
    }

# ============================================================================
# ROUTERS
# ============================================================================

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Include WebSocket router
app.include_router(websocket_router, prefix="/api/v1")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "com.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
