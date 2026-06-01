#!/usr/bin/env python3
"""
cli.py – Command-line interface for the Binance Futures Testnet Trading Bot.

Usage examples:
  python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001
  python cli.py place --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 95000
  python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 90000
  python cli.py account
  python cli.py orders --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from dotenv import load_dotenv

from bot import (
    BinanceClient,
    BinanceAPIError,
    dispatch_order,
    validate_all,
    setup_logging,
    get_logger,
)

# ── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()

# Logging is initialised before anything else so every layer can log.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
setup_logging(LOG_LEVEL)
logger = get_logger("cli")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _print_section(title: str, width: int = 47) -> None:
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def _get_client() -> BinanceClient:
    """Build a BinanceClient from environment variables."""
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        print(
            "\n[ERROR] Missing API credentials.\n"
            "Set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file "
            "or as environment variables.\n"
        )
        logger.error("API credentials not found in environment.")
        sys.exit(1)

    return BinanceClient(api_key=api_key, api_secret=api_secret)


# ── Sub-command handlers ──────────────────────────────────────────────────────

def cmd_place(args: argparse.Namespace) -> None:
    """Handle the 'place' sub-command."""
    _print_section("ORDER REQUEST SUMMARY")
    print(f"  Symbol     : {args.symbol.upper()}")
    print(f"  Side       : {args.side.upper()}")
    print(f"  Type       : {args.type.upper()}")
    print(f"  Quantity   : {args.qty}")
    if args.price:
        print(f"  Price      : {args.price}")
    if args.stop_price:
        print(f"  Stop Price : {args.stop_price}")
    if args.tif:
        print(f"  TIF        : {args.tif}")

    # Validate inputs
    try:
        params = validate_all(
            symbol=args.symbol,
            side=args.side,
            order_type=args.type,
            quantity=args.qty,
            price=args.price,
            stop_price=args.stop_price,
        )
    except ValueError as exc:
        print(f"\n[VALIDATION ERROR] {exc}\n")
        logger.warning("Validation failed: %s", exc)
        sys.exit(1)

    logger.info(
        "CLI place | symbol=%s side=%s type=%s qty=%s price=%s stop=%s",
        params["symbol"], params["side"], params["order_type"],
        params["quantity"], params["price"], params["stop_price"],
    )

    client = _get_client()

    try:
        result = dispatch_order(
            client=client,
            symbol=params["symbol"],
            side=params["side"],
            order_type=params["order_type"],
            quantity=params["quantity"],
            price=params["price"],
            stop_price=params["stop_price"],
            time_in_force=args.tif or "GTC",
        )
    except BinanceAPIError as exc:
        print(f"\n[API ERROR] {exc.message}  (code: {exc.code})\n")
        logger.error("BinanceAPIError: code=%s msg=%s", exc.code, exc.message)
        sys.exit(1)
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {exc}\n")
        logger.exception("Unexpected error during order placement: %s", exc)
        sys.exit(1)

    print(result.display())

    if args.raw:
        _print_section("RAW API RESPONSE")
        print(json.dumps(result.raw, indent=2))

    print("✅  Order submitted successfully.\n")
    logger.info("Order placed successfully | orderId=%s status=%s", result.order_id, result.status)


def cmd_account(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Handle the 'account' sub-command – print account summary."""
    client = _get_client()
    _print_section("ACCOUNT INFORMATION")
    try:
        data = client.get_account()
    except BinanceAPIError as exc:
        print(f"\n[API ERROR] {exc.message}  (code: {exc.code})\n")
        logger.error("get_account error: %s", exc)
        sys.exit(1)

    print(f"  Can Trade  : {data.get('canTrade')}")
    print(f"  Total WB   : {data.get('totalWalletBalance')} USDT")
    print(f"  Avail Bal  : {data.get('availableBalance')} USDT")
    print(f"  Unrealised : {data.get('totalUnrealizedProfit')} USDT")
    print()


def cmd_open_orders(args: argparse.Namespace) -> None:
    """Handle the 'orders' sub-command – list open orders."""
    client = _get_client()
    symbol: Optional[str] = args.symbol.upper() if args.symbol else None
    _print_section(f"OPEN ORDERS{' – ' + symbol if symbol else ''}")
    try:
        orders = client.get_open_orders(symbol=symbol)
    except BinanceAPIError as exc:
        print(f"\n[API ERROR] {exc.message}  (code: {exc.code})\n")
        sys.exit(1)

    if not orders:
        print("  No open orders found.\n")
        return

    for o in orders:
        print(
            f"  [{o.get('orderId')}] {o.get('symbol')} "
            f"{o.get('side')} {o.get('type')} "
            f"qty={o.get('origQty')} price={o.get('price')} "
            f"status={o.get('status')}"
        )
    print()


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description="Binance Futures Testnet – Trading Bot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Market buy:
    python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

  Limit sell:
    python cli.py place --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 95000

  Stop-market sell (bonus):
    python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 90000

  Account info:
    python cli.py account

  List open orders:
    python cli.py orders --symbol BTCUSDT
        """,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ── place ──────────────────────────────────────────────────────────────
    place_p = subparsers.add_parser("place", help="Place a new order")
    place_p.add_argument(
        "--symbol", required=True,
        help="Trading pair, e.g. BTCUSDT"
    )
    place_p.add_argument(
        "--side", required=True,
        choices=["BUY", "SELL", "buy", "sell"],
        help="Order side: BUY or SELL"
    )
    place_p.add_argument(
        "--type", required=True,
        choices=["MARKET", "LIMIT", "STOP_MARKET",
                 "market", "limit", "stop_market"],
        dest="type",
        help="Order type: MARKET | LIMIT | STOP_MARKET"
    )
    place_p.add_argument(
        "--qty", required=True, type=float,
        help="Order quantity (contracts)"
    )
    place_p.add_argument(
        "--price", type=float, default=None,
        help="Limit price (required for LIMIT orders)"
    )
    place_p.add_argument(
        "--stop-price", dest="stop_price", type=float, default=None,
        help="Stop trigger price (required for STOP_MARKET orders)"
    )
    place_p.add_argument(
        "--tif", default="GTC",
        choices=["GTC", "IOC", "FOK", "GTX"],
        help="Time-in-force for LIMIT orders (default: GTC)"
    )
    place_p.add_argument(
        "--raw", action="store_true",
        help="Also print the raw JSON response from the API"
    )
    place_p.set_defaults(func=cmd_place)

    # ── account ────────────────────────────────────────────────────────────
    acc_p = subparsers.add_parser("account", help="Show account balance summary")
    acc_p.set_defaults(func=cmd_account)

    # ── orders ─────────────────────────────────────────────────────────────
    ord_p = subparsers.add_parser("orders", help="List open orders")
    ord_p.add_argument("--symbol", default=None, help="Filter by symbol")
    ord_p.set_defaults(func=cmd_open_orders)

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logger.info("CLI invoked | command=%s", args.command)
    args.func(args)


if __name__ == "__main__":
    main()
