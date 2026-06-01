#!/usr/bin/env python3
"""
gui.py – A zero-dependency lightweight Web UI server for the Binance Futures Trading Bot.
Serves a sleek dashboard at http://localhost:8000.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from decimal import Decimal

from dotenv import load_dotenv

# Ensure root dir is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from bot import (
    BinanceClient,
    BinanceAPIError,
    dispatch_order,
    validate_all,
    setup_logging,
    get_logger,
)

load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
setup_logging(LOG_LEVEL)
logger = get_logger("gui")

def get_binance_client() -> BinanceClient:
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise ValueError("Missing API credentials in .env")
    return BinanceClient(api_key=api_key, api_secret=api_secret)


class DashboardHandler(BaseHTTPRequestHandler):
    """Handles static file serving and REST API endpoints."""

    def log_message(self, format, *args):
        # Override to suppress standard HTTP logging in the console for cleaner bot logs
        logger.debug(format % args)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        
        # ── API Endpoints ───────────────────────────────────────────────────
        
        if parsed_url.path == "/api/account":
            self.handle_api_account()
        elif parsed_url.path == "/api/orders":
            self.handle_api_orders(parsed_url.query)
        elif parsed_url.path == "/api/logs":
            self.handle_api_logs()
        
        # ── Static File Server ──────────────────────────────────────────────
        elif parsed_url.path in ("", "/", "/index.html"):
            self.serve_file("index.html", "text/html")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == "/api/place":
            self.handle_api_place()
        else:
            self.send_error(404, "Endpoint Not Found")

    # ── API Handler Implementations ────────────────────────────────────────

    def send_json(self, data: dict | list, status_code: int = 200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))

    def serve_file(self, filename: str, content_type: str):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except FileNotFoundError:
            self.send_error(404, f"File {filename} not found")

    def handle_api_account(self):
        try:
            client = get_binance_client()
            data = client.get_account()
            self.send_json({
                "status": "success",
                "canTrade": data.get("canTrade"),
                "totalWalletBalance": data.get("totalWalletBalance"),
                "availableBalance": data.get("availableBalance"),
                "totalUnrealizedProfit": data.get("totalUnrealizedProfit")
            })
        except ValueError as exc:
            self.send_json({"status": "error", "message": str(exc)}, 400)
        except BinanceAPIError as exc:
            self.send_json({"status": "error", "message": exc.message, "code": exc.code}, 400)
        except Exception as exc:
            self.send_json({"status": "error", "message": f"Unexpected error: {exc}"}, 500)

    def handle_api_orders(self, query_string: str):
        params = parse_qs(query_string)
        symbol = params.get("symbol", [None])[0]
        if symbol:
            symbol = symbol.upper()

        try:
            client = get_binance_client()
            orders = client.get_open_orders(symbol=symbol)
            self.send_json({"status": "success", "orders": orders})
        except ValueError as exc:
            self.send_json({"status": "error", "message": str(exc)}, 400)
        except BinanceAPIError as exc:
            self.send_json({"status": "error", "message": exc.message, "code": exc.code}, 400)
        except Exception as exc:
            self.send_json({"status": "error", "message": f"Unexpected error: {exc}"}, 500)

    def handle_api_logs(self):
        try:
            log_path = os.path.join(os.path.dirname(__file__), "logs", "trading_bot.log")
            if not os.path.exists(log_path):
                self.send_json({"status": "success", "logs": []})
                return
            
            with open(log_path, "r", encoding="utf-8") as f:
                # Read last 50 log lines
                lines = f.readlines()[-50:]
            
            self.send_json({"status": "success", "logs": [line.strip() for line in lines]})
        except Exception as exc:
            self.send_json({"status": "error", "message": str(exc)}, 500)

    def handle_api_place(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        
        try:
            payload = json.loads(post_data)
        except json.JSONDecodeError:
            self.send_json({"status": "error", "message": "Invalid JSON request payload"}, 400)
            return

        symbol = payload.get("symbol", "")
        side = payload.get("side", "")
        order_type = payload.get("type", "")
        qty = payload.get("qty")
        price = payload.get("price")
        stop_price = payload.get("stop_price")
        tif = payload.get("tif", "GTC")

        # Validation
        try:
            valid_params = validate_all(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=qty,
                price=price,
                stop_price=stop_price,
            )
        except ValueError as exc:
            self.send_json({"status": "validation_error", "message": str(exc)}, 400)
            return

        try:
            client = get_binance_client()
            result = dispatch_order(
                client=client,
                symbol=valid_params["symbol"],
                side=valid_params["side"],
                order_type=valid_params["order_type"],
                quantity=valid_params["quantity"],
                price=valid_params["price"],
                stop_price=valid_params["stop_price"],
                time_in_force=tif,
            )
            self.send_json({
                "status": "success",
                "message": "Order submitted successfully.",
                "data": result.raw
            })
        except ValueError as exc:
            self.send_json({"status": "error", "message": str(exc)}, 400)
        except BinanceAPIError as exc:
            self.send_json({"status": "api_error", "message": exc.message, "code": exc.code}, 400)
        except Exception as exc:
            self.send_json({"status": "error", "message": f"Unexpected error: {exc}"}, 500)


def run_server(port: int = 8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"\n[INFO] Binance Futures Bot UI active at http://localhost:{port}")
    print("Press Ctrl+C to terminate.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    port_arg = 8000
    if len(sys.argv) > 1:
        try:
            port_arg = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port_arg)
