"""
Database configuration and models for COM backend
"""
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.sql import func
import uuid
from datetime import datetime

from ..config import get_settings

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE ENGINE & SESSION
# ============================================================================

def get_database_engine():
    """Get database engine with current settings"""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_recycle=300,
        # SQLite-specific configuration
        connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    )

# Lazy engine creation - will be created when first accessed
_engine = None

def get_engine():
    """Get the database engine, creating it if needed"""
    global _engine
    if _engine is None:
        _engine = get_database_engine()
    return _engine

# Don't create engine at module level

def get_async_session_local():
    """Get async session maker with current engine"""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )

# Don't create session maker at module level

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session"""
    async with get_async_session_local()() as session:
        try:
            yield session
        finally:
            await session.close()

# ============================================================================
# BASE MODEL
# ============================================================================

class Base(DeclarativeBase):
    """Base class for all models"""
    pass

# ============================================================================
# CORE ENTITIES
# ============================================================================

class Order(Base):
    """Order entity"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    order_ref = Column(String(50), unique=True, nullable=False, index=True)
    strategy_id = Column(String(100), nullable=False, index=True)
    instance_id = Column(String(100), nullable=False)
    owner = Column(String(100), nullable=False)
    
    # Instrument details
    symbol = Column(String(20), nullable=False, index=True)
    instrument_class = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)
    
    # Order parameters
    quantity = Column(Float, nullable=False)
    price = Column(Float)
    stop_price = Column(Float)
    time_in_force = Column(String(10), nullable=False)
    expire_at = Column(DateTime)
    
    # Flags
    post_only = Column(Boolean, default=True)
    reduce_only = Column(Boolean, default=False)
    hidden = Column(Boolean, default=False)
    allow_partial_fills = Column(Boolean, default=True)
    
    # State
    state = Column(String(20), nullable=False, default="NEW", index=True)
    broker = Column(String(50))
    broker_order_id = Column(String(100))
    venue = Column(String(50))
    
    # Risk and routing
    risk_config = Column(Text)  # Store as JSON string for SQLite compatibility
    routing_config = Column(Text)  # Store as JSON string for SQLite compatibility
    leverage_config = Column(Text)  # Store as JSON string for SQLite compatibility
    exit_plan = Column(Text)  # Store as JSON string for SQLite compatibility
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    position_ref = Column(String(50), ForeignKey("positions.position_ref"))
    
    # Indexes
    __table_args__ = (
        Index('idx_orders_strategy_symbol_state', 'strategy_id', 'symbol', 'state'),
        Index('idx_orders_strategy_created', 'strategy_id', 'created_at'),
        Index('idx_orders_broker_order', 'broker', 'broker_order_id'),
    )

class Position(Base):
    """Position entity"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    position_ref = Column(String(50), unique=True, nullable=False, index=True)
    strategy_id = Column(String(100), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    
    # Position state
    state = Column(String(20), nullable=False, default="OPEN", index=True)
    
    # Position details
    avg_entry = Column(Float)
    net_qty = Column(Float, default=0.0)
    net_notional = Column(Float)
    
    # Leverage
    leverage_config = Column(Text)  # Store as JSON string for SQLite compatibility
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    closed_at = Column(DateTime)
    
    # Indexes
    __table_args__ = (
        Index('idx_positions_strategy_symbol', 'strategy_id', 'symbol'),
        Index('idx_positions_strategy_state', 'strategy_id', 'state'),
    )

class SubOrder(Base):
    """Suborder entity for exit plan legs"""
    __tablename__ = "suborders"
    
    id = Column(Integer, primary_key=True)
    sub_order_ref = Column(String(50), unique=True, nullable=False, index=True)
    position_ref = Column(String(50), ForeignKey("positions.position_ref"), nullable=False)
    
    # Suborder details
    kind = Column(String(10), nullable=False)  # TP or SL
    label = Column(String(100))
    state = Column(String(20), nullable=False, default="PENDING", index=True)
    
    # Configuration
    allocation = Column(Text, nullable=False)  # Store as JSON string for SQLite compatibility
    trigger = Column(Text, nullable=False)  # Store as JSON string for SQLite compatibility
    exec_config = Column(Text, nullable=False)  # Store as JSON string for SQLite compatibility
    after_fill_actions = Column(Text)  # Store as JSON string for SQLite compatibility
    
    # Broker details
    broker_order_id = Column(String(100))
    
    # Execution details
    filled_qty = Column(Float, default=0.0)
    remaining_qty = Column(Float)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_suborders_position_state', 'position_ref', 'state'),
        Index('idx_suborders_broker_order', 'broker_order_id'),
    )

class Fill(Base):
    """Fill entity for order executions"""
    __tablename__ = "fills"
    
    id = Column(Integer, primary_key=True)
    fill_id = Column(String(100), unique=True, nullable=False)
    order_ref = Column(String(50), ForeignKey("orders.order_ref"), nullable=False)
    
    # Fill details
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    liquidity = Column(String(10), nullable=False)  # MAKER, TAKER, MIXED
    
    # Fees
    fee_amount = Column(Float)
    fee_currency = Column(String(10))
    
    # Timestamps
    filled_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_fills_order_ref', 'order_ref'),
        Index('idx_fills_filled_at', 'filled_at'),
    )

class Event(Base):
    """Event entity for WebSocket broadcasting"""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True)
    event_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    
    # References
    order_ref = Column(String(50), ForeignKey("orders.order_ref"), nullable=False)
    position_ref = Column(String(50), ForeignKey("positions.position_ref"))
    sub_order_ref = Column(String(50), ForeignKey("suborders.sub_order_ref"))
    
    # Event data
    state = Column(String(20))
    details = Column(Text)  # Store as JSON string for SQLite compatibility
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_events_type_occurred', 'event_type', 'occurred_at'),
        Index('idx_events_order_ref', 'order_ref'),
        Index('idx_events_strategy_occurred', 'occurred_at'),
    )

class IdempotencyRecord(Base):
    """Idempotency tracking"""
    __tablename__ = "idempotency_records"
    
    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(200), unique=True, nullable=False, index=True)
    
    # Request details
    payload_hash = Column(String(64), nullable=False)  # SHA256 hash
    request_type = Column(String(50), nullable=False)  # CREATE_ORDER, AMEND_ORDER, etc.
    
    # Result
    result_ref = Column(String(50), nullable=False)  # order_ref, position_ref, etc.
    result_data = Column(Text)  # Store as JSON string for SQLite compatibility
    
    # Timestamps
    first_seen_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_idempotency_expires', 'expires_at'),
        Index('idx_idempotency_request_type', 'request_type'),
    )

class ApiKey(Base):
    """API key management"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True)
    key_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Key details
    name = Column(String(100), nullable=False)
    owner = Column(String(100), nullable=False)
    permissions = Column(Text, nullable=False)  # Store as JSON string for SQLite compatibility
    
    # Security - Store both the actual secret and a hash
    secret_key = Column(String(500), nullable=False)  # Actual secret key for HMAC
    secret_hash = Column(String(255), nullable=False)  # bcrypt hash for verification
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=1000)
    rate_limit_per_hour = Column(Integer, default=10000)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    
    # Indexes
    __table_args__ = (
        Index('idx_api_keys_owner', 'owner'),
        Index('idx_api_keys_active', 'is_active'),
    )

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

async def init_db():
    """Initialize database tables"""
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

async def close_db():
    """Close database connections"""
    engine = get_engine()
    await engine.dispose()
    logger.info("Database connections closed")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_order_ref() -> str:
    """Generate unique order reference"""
    return f"ord_{uuid.uuid4().hex[:16]}"

def generate_position_ref() -> str:
    """Generate unique position reference"""
    return f"pos_{uuid.uuid4().hex[:16]}"

def generate_sub_order_ref() -> str:
    """Generate unique suborder reference"""
    return f"sub_{uuid.uuid4().hex[:16]}"
