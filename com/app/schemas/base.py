"""
Core Pydantic schemas and enums for COM
Matches the JSON schema specification exactly
"""
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum

# ============================================================================
# CORE ENUMS
# ============================================================================

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    LIMIT_IF_TOUCHED = "LIMIT_IF_TOUCHED"

class TimeInForce(str, Enum):
    GTC = "GTC"  # Good Till Cancelled
    DAY = "DAY"  # Day order
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTD = "GTD"  # Good Till Date

class InstrumentClass(str, Enum):
    EQUITY = "equity"
    OPTION = "option"
    FUTURE = "future"
    CRYPTO_SPOT = "crypto_spot"
    CRYPTO_PERP = "crypto_perp"
    FX = "fx"

class MarketType(str, Enum):
    """Market type for balance queries"""
    CRYPTO = "crypto"
    EQUITIES = "equities"
    FUTURES = "futures"
    FX = "fx"

class RiskSizingMode(str, Enum):
    USD = "USD"
    PCT_BALANCE = "PCT_BALANCE"  # Percentage of total balance
    PCT_BROKER = "PCT_BROKER"    # Percentage of broker balance
    PCT_ALL = "PCT_ALL"          # Percentage of all accounts
    PCT_MARKET = "PCT_MARKET"    # Percentage of market balance

class RoutingMode(str, Enum):
    AUTO = "AUTO"
    DIRECT = "DIRECT"

class ExitLegKind(str, Enum):
    TP = "TP"  # Take Profit
    SL = "SL"  # Stop Loss

class TriggerMode(str, Enum):
    PRICE = "PRICE"
    PERCENT_FROM_ENTRY = "PERCENT_FROM_ENTRY"
    TRAIL = "TRAIL"
    RATCHET = "RATCHET"

class TriggerPriceType(str, Enum):
    MARK = "MARK"
    LAST = "LAST"
    BID = "BID"
    ASK = "ASK"
    MID = "MID"

class ExecuteOrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"

class AfterFillAction(str, Enum):
    SET_SL_TO_BREAKEVEN = "SET_SL_TO_BREAKEVEN"
    START_TRAILING_SL = "START_TRAILING_SL"

class OrderState(str, Enum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class PositionState(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"

class SubOrderState(str, Enum):
    PENDING = "PENDING"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    TRIGGERED = "TRIGGERED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class Liquidity(str, Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"
    MIXED = "MIXED"

class EventType(str, Enum):
    ORDER_UPDATE = "ORDER_UPDATE"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    TAKE_PROFIT_TRIGGERED = "TAKE_PROFIT_TRIGGERED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_CLEANUP = "POSITION_CLEANUP"
    HEARTBEAT = "HEARTBEAT"

class ErrorCode(str, Enum):
    INVALID_SCHEMA = "INVALID_SCHEMA"
    AUTH_FAILED = "AUTH_FAILED"
    CLOCK_SKEW = "CLOCK_SKEW"
    DUPLICATE_IDEMPOTENCY_KEY = "DUPLICATE_IDEMPOTENCY_KEY"
    DUPLICATE_INTENT = "DUPLICATE_INTENT"
    RISK_CHECK_FAILED = "RISK_CHECK_FAILED"
    PRICE_BOUNDS = "PRICE_BOUNDS"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    ROUTING_UNAVAILABLE = "ROUTING_UNAVAILABLE"
    BROKER_DOWN = "BROKER_DOWN"
    POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
    POSITION_AMBIGUOUS = "POSITION_AMBIGUOUS"
    NOT_REDUCING_EXPOSURE = "NOT_REDUCING_EXPOSURE"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"
    TIMEINFORCE_UNSUPPORTED = "TIMEINFORCE_UNSUPPORTED"
    MAINTENANCE_WINDOW = "MAINTENANCE_WINDOW"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

# ============================================================================
# BASE MODELS
# ============================================================================

class Environment(BaseModel):
    """Environment configuration"""
    sandbox: bool = Field(description="True for paper trading, False for live")
    
    model_config = ConfigDict(extra="forbid")

class Source(BaseModel):
    """Request source information"""
    strategy_id: str = Field(description="Unique strategy identifier")
    instance_id: str = Field(description="Strategy instance identifier")
    owner: str = Field(description="Strategy owner identifier")
    
    model_config = ConfigDict(extra="forbid")

class Instrument(BaseModel):
    """Trading instrument definition"""
    class_: InstrumentClass = Field(alias="class", description="Instrument class")
    symbol: str = Field(description="Trading symbol")
    currency: Optional[str] = Field(default=None, description="Quote currency")
    contract: Optional[Dict[str, Any]] = Field(default=None, description="Contract details")
    
    model_config = ConfigDict(extra="forbid")

class Quantity(BaseModel):
    """Order quantity specification"""
    type: str = Field(description="Quantity type: base_units, quote_notional, contracts")
    value: float = Field(gt=0, description="Quantity value")
    
    model_config = ConfigDict(extra="forbid")

class Flags(BaseModel):
    """Order flags and modifiers"""
    post_only: bool = Field(description="Post-only order")
    reduce_only: bool = Field(description="Reduce-only order")
    hidden: bool = Field(description="Hidden order")
    iceberg: Dict[str, Any] = Field(description="Iceberg order settings")
    allow_partial_fills: bool = Field(description="Allow partial fills")
    
    model_config = ConfigDict(extra="forbid")

class RiskGuards(BaseModel):
    """Risk management guards"""
    max_slippage_bps: Optional[float] = Field(default=None, ge=0, description="Max slippage in basis points")
    max_spread_bps: Optional[float] = Field(default=None, ge=0, description="Max spread in basis points")
    price_bounds: Optional[Dict[str, Optional[float]]] = Field(default=None, description="Price bounds")
    max_fees_quote: Optional[float] = Field(default=None, ge=0, description="Max fees in quote currency")
    min_fill_pct: Optional[float] = Field(default=None, ge=0, le=100, description="Minimum fill percentage")
    
    model_config = ConfigDict(extra="forbid")

class RiskSizing(BaseModel):
    """Risk-based sizing configuration"""
    mode: RiskSizingMode = Field(description="Sizing mode")
    value: float = Field(gt=0, description="Sizing value")
    broker: Optional[str] = Field(default=None, description="Broker for PCT_BROKER mode")
    market: Optional[str] = Field(default=None, description="Market for PCT_MARKET mode")
    cap: Optional[Dict[str, Optional[float]]] = Field(default=None, description="Upper limits")
    floor: Optional[Dict[str, Optional[float]]] = Field(default=None, description="Lower limits")
    
    model_config = ConfigDict(extra="forbid")

class Risk(BaseModel):
    """Risk management configuration"""
    sizing: Optional[RiskSizing] = Field(default=None, description="Risk-based sizing")
    guards: Optional[RiskGuards] = Field(default=None, description="Risk guards")
    
    model_config = ConfigDict(extra="forbid")

class Routing(BaseModel):
    """Order routing configuration"""
    mode: RoutingMode = Field(default=RoutingMode.AUTO, description="Routing mode")
    direct: Optional[Dict[str, str]] = Field(default=None, description="Direct routing settings")
    policy: Optional[Dict[str, Any]] = Field(default=None, description="Routing policy")
    hints: Optional[Dict[str, Any]] = Field(default=None, description="Routing hints")
    
    model_config = ConfigDict(extra="forbid")

class Leverage(BaseModel):
    """Leverage configuration"""
    enabled: bool = Field(description="Leverage enabled")
    leverage: Optional[float] = Field(default=None, ge=1, description="Leverage multiplier")
    margin_type: Optional[str] = Field(default=None, description="Margin type: isolated, cross")
    
    model_config = ConfigDict(extra="forbid")

class ExitLeg(BaseModel):
    """Exit plan leg definition"""
    kind: ExitLegKind = Field(description="Leg type: TP or SL")
    label: Optional[str] = Field(default=None, description="Leg label")
    allocation: Dict[str, Any] = Field(description="Allocation settings")
    trigger: Dict[str, Any] = Field(description="Trigger configuration")
    exec: Dict[str, Any] = Field(description="Execution configuration")
    after_fill_actions: Optional[List[Dict[str, Any]]] = Field(default=None, description="After-fill actions")
    
    model_config = ConfigDict(extra="forbid")

class ExitPlan(BaseModel):
    """Exit plan configuration"""
    legs: List[ExitLeg] = Field(min_length=1, description="Exit plan legs")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# REQUEST MODELS
# ============================================================================

class OrderRequest(BaseModel):
    """Order creation request"""
    instrument: Instrument = Field(description="Trading instrument")
    side: OrderSide = Field(description="Order side")
    quantity: Optional[Quantity] = Field(default=None, description="Order quantity")
    order_type: OrderType = Field(description="Order type")
    price: Optional[float] = Field(default=None, description="Limit price")
    stop_price: Optional[float] = Field(default=None, description="Stop price")
    time_in_force: TimeInForce = Field(description="Time in force")
    expire_at: Optional[datetime] = Field(default=None, description="Expiration time")
    flags: Flags = Field(description="Order flags")
    risk: Optional[Risk] = Field(default=None, description="Risk configuration")
    exit_plan: Optional[ExitPlan] = Field(default=None, description="Exit plan")
    routing: Routing = Field(description="Routing configuration")
    leverage: Leverage = Field(description="Leverage configuration")
    
    model_config = ConfigDict(extra="forbid")
    
    def model_post_init(self, __context: Any) -> None:
        """Validate order requirements"""
        # LIMIT orders require price
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require price")
        
        # STOP orders require stop_price
        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and self.stop_price is None:
            raise ValueError(f"{self.order_type} orders require stop_price")
        
        # Exactly one of quantity or risk.sizing
        if (self.quantity is None) == (self.risk is None or self.risk.sizing is None):
            raise ValueError("Exactly one of quantity or risk.sizing must be provided")

class AmendOrderRequest(BaseModel):
    """Order amendment request"""
    price: Optional[float] = Field(default=None, description="New price")
    quantity: Optional[Quantity] = Field(default=None, description="New quantity")
    time_in_force: Optional[TimeInForce] = Field(default=None, description="New time in force")
    flags: Optional[Flags] = Field(default=None, description="New flags")
    
    model_config = ConfigDict(extra="forbid")

class CreateSubOrderRequest(BaseModel):
    """Suborder creation request"""
    leg: ExitLeg = Field(description="Exit plan leg")
    
    model_config = ConfigDict(extra="forbid")

class AmendSubOrderRequest(BaseModel):
    """Suborder amendment request"""
    trigger: Optional[Dict[str, Any]] = Field(default=None, description="New trigger settings")
    exec: Optional[Dict[str, Any]] = Field(default=None, description="New execution settings")
    allocation: Optional[Dict[str, Any]] = Field(default=None, description="New allocation settings")
    after_fill_actions: Optional[List[Dict[str, Any]]] = Field(default=None, description="New after-fill actions")
    
    model_config = ConfigDict(extra="forbid")

class ClosePositionRequest(BaseModel):
    """Position close request"""
    amount: Dict[str, Any] = Field(description="Close amount specification")
    order: Dict[str, Any] = Field(description="Close order specification")
    guards: Optional[RiskGuards] = Field(default=None, description="Risk guards")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ErrorEnvelope(BaseModel):
    """Error response envelope"""
    error: Dict[str, Any] = Field(description="Error details")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Error context")
    
    model_config = ConfigDict(extra="forbid")

class Ack(BaseModel):
    """Acknowledgement response"""
    status: str = Field(description="Status: ACK or REJECT")
    received_at: Optional[datetime] = Field(default=None, description="Request received time")
    environment: Optional[Environment] = Field(default=None, description="Environment")
    order_ref: Optional[str] = Field(default=None, description="Order reference")
    position_ref: Optional[str] = Field(default=None, description="Position reference")
    sub_order_ref: Optional[str] = Field(default=None, description="Suborder reference")
    reason: Optional[str] = Field(default=None, description="Rejection reason")
    adjustments: Optional[Dict[str, Any]] = Field(default=None, description="Price/quantity adjustments")
    
    model_config = ConfigDict(extra="forbid")

class OrderView(BaseModel):
    """Order view response"""
    order_ref: str = Field(description="Order reference")
    state: OrderState = Field(description="Order state")
    source: Source = Field(description="Order source")
    instrument: Instrument = Field(description="Trading instrument")
    side: OrderSide = Field(description="Order side")
    quantity: Optional[Quantity] = Field(default=None, description="Order quantity")
    order_type: OrderType = Field(description="Order type")
    price: Optional[float] = Field(default=None, description="Limit price")
    stop_price: Optional[float] = Field(default=None, description="Stop price")
    time_in_force: TimeInForce = Field(description="Time in force")
    flags: Flags = Field(description="Order flags")
    routing: Routing = Field(description="Routing configuration")
    leverage: Leverage = Field(description="Leverage configuration")
    risk: Optional[Risk] = Field(default=None, description="Risk configuration")
    exit_plan: Optional[ExitPlan] = Field(default=None, description="Exit plan")
    position_ref: Optional[str] = Field(default=None, description="Position reference")
    broker: Optional[str] = Field(default=None, description="Broker name")
    venue: Optional[str] = Field(default=None, description="Trading venue")
    broker_order_id: Optional[str] = Field(default=None, description="Broker order ID")
    created_at: Optional[datetime] = Field(default=None, description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")
    fills_summary: Optional[Dict[str, Any]] = Field(default=None, description="Fills summary")
    
    model_config = ConfigDict(extra="forbid")

class SubOrderView(BaseModel):
    """Suborder view response"""
    sub_order_ref: str = Field(description="Suborder reference")
    position_ref: str = Field(description="Position reference")
    kind: ExitLegKind = Field(description="Leg type")
    state: SubOrderState = Field(description="Suborder state")
    allocation: Dict[str, Any] = Field(description="Allocation settings")
    trigger: Dict[str, Any] = Field(description="Trigger configuration")
    exec: Dict[str, Any] = Field(description="Execution configuration")
    label: Optional[str] = Field(default=None, description="Leg label")
    broker_order_id: Optional[str] = Field(default=None, description="Broker order ID")
    filled_qty: Optional[float] = Field(default=None, description="Filled quantity")
    remaining_qty: Optional[float] = Field(default=None, description="Remaining quantity")
    
    model_config = ConfigDict(extra="forbid")

class PositionView(BaseModel):
    """Position view response"""
    position_ref: str = Field(description="Position reference")
    strategy_id: str = Field(description="Strategy identifier")
    symbol: str = Field(description="Trading symbol")
    state: PositionState = Field(description="Position state")
    avg_entry: Optional[float] = Field(default=None, description="Average entry price")
    net_qty: Optional[float] = Field(default=None, description="Net quantity")
    net_notional: Optional[float] = Field(default=None, description="Net notional value")
    created_at: Optional[datetime] = Field(default=None, description="Creation time")
    closed_at: Optional[datetime] = Field(default=None, description="Close time")
    leverage: Optional[Leverage] = Field(default=None, description="Leverage configuration")
    suborders: List[SubOrderView] = Field(default_factory=list, description="Linked suborders")
    
    model_config = ConfigDict(extra="forbid")

class WSEvent(BaseModel):
    """WebSocket event"""
    event_type: EventType = Field(description="Event type")
    occurred_at: datetime = Field(description="Event occurrence time")
    order_ref: str = Field(description="Order reference")
    position_ref: Optional[str] = Field(default=None, description="Position reference")
    sub_order_ref: Optional[str] = Field(default=None, description="Suborder reference")
    state: Optional[str] = Field(default=None, description="New state")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Event details")
    
    model_config = ConfigDict(extra="forbid")
