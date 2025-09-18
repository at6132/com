"""
Balances API endpoints
Balance queries and snapshots
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import logging

from ...core.database import get_db
from ...schemas.balances import (
    BalancesOverviewResponse, BalancesPerBrokerResponse, BalancesPerMarketResponse
)
from ...schemas.base import MarketType

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/algo/{strategy_id}", response_model=Dict[str, Any])
async def get_algo_balance(
    strategy_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get balance for a specific algo/strategy"""
    try:
        from ...services.balance_tracker import balance_tracker
        
        logger.info(f"📊 Fetching balance for algo: {strategy_id}")
        
        # Get balance data from balance tracker
        balance_data = await balance_tracker.get_strategy_balance(strategy_id)
        
        if not balance_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No balance data found for strategy {strategy_id}"
            )
        
        return {
            "strategy_id": strategy_id,
            "balance": balance_data.get("balance", 0.0),
            "available": balance_data.get("available", 0.0),
            "margin_used": balance_data.get("margin_used", 0.0),
            "unrealized_pnl": balance_data.get("unrealized_pnl", 0.0),
            "realized_pnl": balance_data.get("realized_pnl", 0.0),
            "daily_pnl": balance_data.get("daily_pnl", 0.0),
            "weekly_pnl": balance_data.get("weekly_pnl", 0.0),
            "monthly_pnl": balance_data.get("monthly_pnl", 0.0),
            "active_positions": balance_data.get("active_positions", 0),
            "total_trades": balance_data.get("total_trades", 0),
            "total_volume": balance_data.get("total_volume", 0.0),
            "last_updated": balance_data.get("last_updated", ""),
            "broker": balance_data.get("broker", "mexc"),
            "account_id": balance_data.get("account_id", "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting algo balance for {strategy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/", response_model=BalancesOverviewResponse)
async def get_balances_overview(
    db: AsyncSession = Depends(get_db)
) -> BalancesOverviewResponse:
    """Balances overview (totals + per-market summary)"""
    try:
        from ...services.balance_tracker import balance_tracker
        
        # Get total balance data
        total_balance_data = await balance_tracker.get_total_balance()
        
        return BalancesOverviewResponse(
            total_balance=total_balance_data.get("total_balance", 0.0),
            total_available=total_balance_data.get("total_available", 0.0),
            total_margin_used=total_balance_data.get("total_margin_used", 0.0),
            total_unrealized_pnl=total_balance_data.get("total_unrealized_pnl", 0.0),
            total_realized_pnl=total_balance_data.get("total_realized_pnl", 0.0),
            total_daily_pnl=total_balance_data.get("total_daily_pnl", 0.0),
            total_weekly_pnl=total_balance_data.get("total_weekly_pnl", 0.0),
            total_monthly_pnl=total_balance_data.get("total_monthly_pnl", 0.0),
            active_positions=total_balance_data.get("active_positions", 0),
            active_strategies=total_balance_data.get("active_strategies", 0),
            active_accounts=total_balance_data.get("active_accounts", 0),
            total_trades=total_balance_data.get("total_trades", 0),
            total_volume=total_balance_data.get("total_volume", 0.0),
            last_updated=total_balance_data.get("last_updated", ""),
            market_summary=total_balance_data.get("market_summary", {})
        )
        
    except Exception as e:
        logger.error(f"❌ Error getting balances overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/brokers", response_model=BalancesPerBrokerResponse)
async def get_broker_balances(
    db: AsyncSession = Depends(get_db)
) -> BalancesPerBrokerResponse:
    """Balances per broker/account"""
    try:
        # TODO: Implement broker balances logic
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/markets", response_model=BalancesPerMarketResponse)
async def get_market_balances(
    market: MarketType = Query(..., description="Market type (crypto|equities|futures|fx)"),
    db: AsyncSession = Depends(get_db)
) -> BalancesPerMarketResponse:
    """Balances aggregated within one market"""
    try:
        # TODO: Implement market balances logic
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
