"""
Low-level Binance Futures Testnet REST client.

Handles:
- HMAC-SHA256 request signing
- Timestamping
- HTTP communication via `requests`
- Response / error parsing
- Full request + response logging
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from .logging_config import get_logger

logger = get_logger("client")

TESTNET_BASE_URL = "https://testnet.binancefuture.com"


class BinanceAPIError(Exception):
    """Raised when the Binance API returns a non-2xx response or an error payload."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Binance API error {code}: {message}")


class BinanceClient:
    """Minimal REST client for Binance USDT-M Futures Testnet."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = TESTNET_BASE_URL,
        timeout: int = 10,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret must not be empty.")
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-MBX-APIKEY": self._api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        logger.info("BinanceClient initialised (base_url=%s)", self._base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, params: dict) -> str:
        query_string = urlencode(params)
        signature = hmac.new(
            self._api_secret, query_string.encode(), hashlib.sha256
        ).hexdigest()
        return signature

    def _build_signed_params(self, params: dict) -> dict:
        params["timestamp"] = self._timestamp()
        params["recvWindow"] = 5000
        params["signature"] = self._sign(params)
        return params

    def _handle_response(self, response: requests.Response) -> dict:
        logger.debug(
            "HTTP %s %s – status %s",
            response.request.method,
            response.url,
            response.status_code,
        )
        try:
            data = response.json()
        except ValueError:
            logger.error("Non-JSON response body: %s", response.text[:500])
            response.raise_for_status()
            return {}

        if not response.ok:
            code = data.get("code", response.status_code)
            msg = data.get("msg", response.text)
            logger.error("API error – code=%s msg=%s", code, msg)
            raise BinanceAPIError(code=code, message=msg)

        logger.debug("Response payload: %s", data)
        return data

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_exchange_info(self) -> dict:
        """Fetch exchange metadata (no auth required)."""
        url = f"{self._base_url}/fapi/v1/exchangeInfo"
        logger.info("GET exchangeInfo")
        resp = self._session.get(url, timeout=self._timeout)
        return self._handle_response(resp)

    def get_account(self) -> dict:
        """Fetch account information (signed)."""
        url = f"{self._base_url}/fapi/v2/account"
        params = self._build_signed_params({})
        logger.info("GET account (signed)")
        resp = self._session.get(url, params=params, timeout=self._timeout)
        return self._handle_response(resp)

    def place_order(self, order_params: dict) -> dict:
        """
        POST a new order to /fapi/v1/order.

        `order_params` should already be validated but NOT yet signed.
        """
        url = f"{self._base_url}/fapi/v1/order"
        params = self._build_signed_params(dict(order_params))

        # Log the outgoing request (mask nothing – testnet only)
        logger.info(
            "POST /fapi/v1/order | request_params=%s",
            {k: v for k, v in params.items() if k != "signature"},
        )

        resp = self._session.post(url, data=params, timeout=self._timeout)
        result = self._handle_response(resp)

        logger.info("Order response: %s", result)
        return result

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order by orderId."""
        url = f"{self._base_url}/fapi/v1/order"
        params = self._build_signed_params({"symbol": symbol, "orderId": order_id})
        logger.info("DELETE /fapi/v1/order | symbol=%s orderId=%s", symbol, order_id)
        resp = self._session.delete(url, params=params, timeout=self._timeout)
        return self._handle_response(resp)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Fetch all open orders, optionally filtered by symbol."""
        url = f"{self._base_url}/fapi/v1/openOrders"
        raw = {"symbol": symbol} if symbol else {}
        params = self._build_signed_params(raw)
        logger.info("GET openOrders | symbol=%s", symbol or "ALL")
        resp = self._session.get(url, params=params, timeout=self._timeout)
        return self._handle_response(resp)
