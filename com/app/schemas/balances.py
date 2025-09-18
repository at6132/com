"""
Balance-specific request and response schemas
Matches the JSON schema specification exactly
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class BalancesOverviewResponse(BaseModel):
    """Balances Overview Response - matches JSON schema exactly"""
    as_of: datetime = Field(description="Balance snapshot time")
    totals: Dict[str, float] = Field(description="Total balances by currency")
    markets: Dict[str, Dict[str, float]] = Field(description="Balances by market and currency")
    
    model_config = ConfigDict(extra="forbid")

class BalancesPerBrokerResponse(BaseModel):
    """Balances Per-Broker Response - matches JSON schema exactly"""
    as_of: datetime = Field(description="Balance snapshot time")
    brokers: List[Dict[str, Any]] = Field(description="Broker balances")
    
    model_config = ConfigDict(extra="forbid")

class BalancesPerMarketResponse(BaseModel):
    """Balances Per-Market Response - matches JSON schema exactly"""
    as_of: datetime = Field(description="Balance snapshot time")
    market: str = Field(description="Market identifier")
    brokers: List[Dict[str, Any]] = Field(description="Broker balances for market")
    aggregate: Dict[str, float] = Field(description="Aggregated balances")
    
    model_config = ConfigDict(extra="forbid")

# ============================================================================
# INTERNAL MODELS
# ============================================================================

class BalanceSnapshot(BaseModel):
    """Internal balance snapshot"""
    snapshot_id: str = Field(description="Snapshot identifier")
    as_of: datetime = Field(description="Snapshot time")
    scope: str = Field(description="Snapshot scope: overview, broker, market")
    payload: Dict[str, Any] = Field(description="Balance data")
    
    model_config = ConfigDict(extra="forbid")

class BrokerBalance(BaseModel):
    """Broker balance information"""
    broker: str = Field(description="Broker name")
    environment: Optional[str] = Field(default=None, description="Environment: LIVE, PAPER")
    balances: Dict[str, float] = Field(description="Currency balances")
    
    model_config = ConfigDict(extra="forbid")

class MarketBalance(BaseModel):
    """Market balance information"""
    market: str = Field(description="Market identifier")
    broker_balances: List[BrokerBalance] = Field(description="Broker balances for market")
    aggregate: Dict[str, float] = Field(description="Aggregated balances")
    
    model_config = ConfigDict(extra="forbid")

class BalanceQuery(BaseModel):
    """Balance query parameters"""
    market: Optional[str] = Field(default=None, description="Filter by market")
    broker: Optional[str] = Field(default=None, description="Filter by broker")
    
    model_config = ConfigDict(extra="forbid")
