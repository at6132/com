"""
Error logging service for COM system
Logs all errors to CSV files for analysis and debugging
"""
import csv
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ErrorLogger:
    """Service for logging errors to CSV files"""
    
    def __init__(self):
        self.logs_dir = Path("Logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.errors_csv = self.logs_dir / "errors.csv"
        self._initialize_csv_headers()
        
    def _initialize_csv_headers(self):
        """Initialize CSV file with headers if it doesn't exist"""
        if not self.errors_csv.exists():
            with open(self.errors_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'error_type',
                    'error_message',
                    'service',
                    'function',
                    'position_id',
                    'order_ref',
                    'strategy_id',
                    'traceback',
                    'context_data'
                ])
    
    def log_error(
        self,
        error: Exception,
        service: str = "unknown",
        function: str = "unknown",
        position_id: Optional[str] = None,
        order_ref: Optional[str] = None,
        strategy_id: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None
    ):
        """Log an error to the CSV file"""
        try:
            error_type = type(error).__name__
            error_message = str(error)
            traceback_str = traceback.format_exc()
            
            # Prepare context data as JSON string
            context_json = json.dumps(context_data) if context_data else ""
            
            # Write to CSV
            with open(self.errors_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.utcnow().isoformat(),
                    error_type,
                    error_message,
                    service,
                    function,
                    position_id or "",
                    order_ref or "",
                    strategy_id or "",
                    traceback_str,
                    context_json
                ])
            
            logger.error(f"📝 Error logged to {self.errors_csv}: {error_type} - {error_message}")
            
        except Exception as e:
            logger.error(f"❌ Failed to log error to CSV: {e}")
    
    def log_timestop_error(
        self,
        error: Exception,
        position_id: str,
        action: str,
        context_data: Optional[Dict[str, Any]] = None
    ):
        """Log timestop-specific errors"""
        self.log_error(
            error=error,
            service="position_tracker",
            function=f"timestop_{action}",
            position_id=position_id,
            context_data={
                "timestop_action": action,
                **(context_data or {})
            }
        )
    
    def log_order_error(
        self,
        error: Exception,
        order_ref: str,
        strategy_id: str,
        function: str = "create_order",
        context_data: Optional[Dict[str, Any]] = None
    ):
        """Log order-specific errors"""
        self.log_error(
            error=error,
            service="orders",
            function=function,
            order_ref=order_ref,
            strategy_id=strategy_id,
            context_data=context_data
        )
    
    def log_position_error(
        self,
        error: Exception,
        position_id: str,
        strategy_id: str,
        function: str = "position_tracking",
        context_data: Optional[Dict[str, Any]] = None
    ):
        """Log position-specific errors"""
        self.log_error(
            error=error,
            service="position_tracker",
            function=function,
            position_id=position_id,
            strategy_id=strategy_id,
            context_data=context_data
        )

# Global error logger instance
error_logger = ErrorLogger()
