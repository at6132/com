#!/usr/bin/env python33
"""
COM System Startup Script
Initializes the entire Central Order Manager system
"""
import asyncio
import sys
import os
import signal
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from com.app.config import get_settings
from com.app.core.logging import setup_logging
from com.app.core.database import init_db, close_db
from com.app.core.redis import init_redis, close_redis
from com.app.adapters.manager import broker_manager

# Global variables for cleanup
logger = None
shutdown_event = asyncio.Event()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()

async def initialize_database():
    """Initialize database connection and tables"""
    try:
        logger.info("Initializing database...")
        await init_db()
        logger.info("✅ Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

async def initialize_redis():
    """Initialize Redis connection"""
    try:
        logger.info("Initializing Redis...")
        await init_redis()
        logger.info("✅ Redis initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Redis initialization failed: {e}")
        return False

async def initialize_brokers():
    """Initialize broker connections"""
    try:
        logger.info("Initializing broker connections...")
        await broker_manager.initialize()
        logger.info("✅ Broker connections initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Broker initialization failed: {e}")
        return False

async def health_check():
    """Perform system health check"""
    try:
        logger.info("Performing system health check...")
        
        # Check database
        try:
            from com.app.core.database import get_db
            async for db in get_db():
                from sqlalchemy import text
                result = await db.execute(text("SELECT 1"))
                assert result.scalar() == 1
                break
            logger.info("✅ Database health check passed")
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return False
        
        # Check Redis
        try:
            from com.app.core.redis import redis_client
            await redis_client.ping()
            logger.info("✅ Redis health check passed")
        except Exception as e:
            logger.error(f"❌ Redis health check failed: {e}")
            return False
        
        # Check brokers
        try:
            enabled_brokers = broker_manager.get_enabled_brokers()
            for name, config in enabled_brokers.items():
                logger.info(f"   - {name}: {config.environment} ({'testnet' if config.testnet else 'live'})")
            logger.info("✅ Broker health check passed")
        except Exception as e:
            logger.error(f"❌ Broker health check failed: {e}")
            return False
        
        logger.info("✅ All health checks passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return False

async def start_fastapi_server():
    """Start the FastAPI server"""
    try:
        logger.info("Starting FastAPI server...")
        
        # Import and start server
        import uvicorn
        from com.app.main import app
        
        config = uvicorn.Config(
            app=app,
            host=get_settings().host,
            port=get_settings().port,
            log_level="info" if get_settings().debug else "warning",
            reload=get_settings().debug,
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        # Start server in background
        server_task = asyncio.create_task(server.serve())
        
        logger.info(f"✅ FastAPI server started on {get_settings().host}:{get_settings().port}")
        return server_task
        
    except Exception as e:
        logger.error(f"❌ FastAPI server startup failed: {e}")
        return None

async def main():
    """Main startup sequence"""
    global logger
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting COM System...")
    logger.info("=" * 60)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get settings
    try:
        settings = get_settings()
        logger.info(f"Configuration loaded:")
        logger.info(f"   Environment: {'Production' if settings.is_production else 'Development'}")
        logger.info(f"   Debug: {settings.debug}")
        logger.info(f"   Host: {settings.host}")
        logger.info(f"   Port: {settings.port}")
        logger.info(f"   Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'configured'}")
        logger.info(f"   Redis: {settings.redis_url.split('@')[-1] if '@' in settings.redis_url else 'configured'}")
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        return 1
    
    # Initialize core services
    logger.info("\n📊 Initializing Core Services...")
    
    if not await initialize_database():
        logger.error("❌ Database initialization failed, aborting startup")
        return 1
    
    if not await initialize_redis():
        logger.error("❌ Redis initialization failed, aborting startup")
        return 1
    
    if not await initialize_brokers():
        logger.error("❌ Broker initialization failed, aborting startup")
        return 1
    
    # Health check
    logger.info("\n🔍 Performing Health Check...")
    if not await health_check():
        logger.error("❌ Health check failed, aborting startup")
        return 1
    
    # Start FastAPI server
    logger.info("\n🌐 Starting Web Server...")
    server_task = await start_fastapi_server()
    if not server_task:
        logger.error("❌ Web server startup failed, aborting startup")
        return 1
    
    # System ready
    logger.info("\n" + "=" * 60)
    logger.info("🎉 COM SYSTEM STARTUP COMPLETE!")
    logger.info("=" * 60)
    logger.info("✅ Database: Connected and initialized")
    logger.info("✅ Redis: Connected and ready")
    logger.info("✅ Brokers: Connected and configured")
    logger.info("✅ Web Server: Running and accepting connections")
    logger.info("✅ API: Available at /docs for testing")
    logger.info("✅ WebSocket: Available at /v1/stream")
    logger.info("=" * 60)
    logger.info("System is now ready to accept orders and manage trading operations")
    logger.info("Press Ctrl+C to shutdown gracefully")
    
    # Wait for shutdown signal
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    
    # Graceful shutdown
    logger.info("\n🔄 Initiating graceful shutdown...")
    
    # Cancel server task
    if server_task:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
    
    # Close connections
    logger.info("Closing broker connections...")
    await broker_manager.shutdown()
    
    logger.info("Closing Redis connection...")
    await close_redis()
    
    logger.info("Closing database connection...")
    await close_db()
    
    logger.info("✅ Shutdown complete")
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
