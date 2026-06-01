"""
trading_bot.bot – core package.
"""

from .client import BinanceClient, BinanceAPIError
from .orders import dispatch_order, OrderResult
from .validators import validate_all
from .logging_config import setup_logging, get_logger

__all__ = [
    "BinanceClient",
    "BinanceAPIError",
    "dispatch_order",
    "OrderResult",
    "validate_all",
    "setup_logging",
    "get_logger",
]
