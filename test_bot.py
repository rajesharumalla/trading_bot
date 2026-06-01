import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import os
import sys

# Ensure the root directory is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_stop_price,
    validate_all,
)
from bot.client import BinanceClient, BinanceAPIError
from bot.orders import OrderResult, dispatch_order
from cli import build_parser, cmd_place, cmd_account, cmd_open_orders


class TestValidators(unittest.TestCase):
    """Verify that input validation logic behaves as expected."""

    def test_validate_symbol(self):
        self.assertEqual(validate_symbol("BTCUSDT"), "BTCUSDT")
        self.assertEqual(validate_symbol(" btcUSDT  "), "BTCUSDT")
        
        # Invalid cases
        with self.assertRaises(ValueError) as ctx:
            validate_symbol("BTC")
        self.assertIn("looks too short", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_symbol("BTC-USDT")
        self.assertIn("contains invalid characters", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_symbol("")
        self.assertIn("must be a non-empty string", str(ctx.exception))

    def test_validate_side(self):
        self.assertEqual(validate_side("BUY"), "BUY")
        self.assertEqual(validate_side("sell"), "SELL")

        with self.assertRaises(ValueError) as ctx:
            validate_side("HOLD")
        self.assertIn("Invalid side 'HOLD'", str(ctx.exception))

    def test_validate_order_type(self):
        self.assertEqual(validate_order_type("MARKET"), "MARKET")
        self.assertEqual(validate_order_type("limit"), "LIMIT")
        self.assertEqual(validate_order_type("stop_market"), "STOP_MARKET")

        with self.assertRaises(ValueError) as ctx:
            validate_order_type("TRAILING_STOP")
        self.assertIn("Invalid order type 'TRAILING_STOP'", str(ctx.exception))

    def test_validate_quantity(self):
        self.assertEqual(validate_quantity(0.001), Decimal("0.001"))
        self.assertEqual(validate_quantity("1.5"), Decimal("1.5"))

        with self.assertRaises(ValueError) as ctx:
            validate_quantity("-0.01")
        self.assertIn("must be greater than zero", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_quantity("abc")
        self.assertIn("is not a valid number", str(ctx.exception))

    def test_validate_price(self):
        # LIMIT order requires price
        self.assertEqual(validate_price(65000, "LIMIT"), Decimal("65000"))
        with self.assertRaises(ValueError) as ctx:
            validate_price(None, "LIMIT")
        self.assertIn("Price is required for LIMIT orders", str(ctx.exception))

        # MARKET order should NOT have price
        self.assertIsNone(validate_price(None, "MARKET"))
        with self.assertRaises(ValueError) as ctx:
            validate_price(65000, "MARKET")
        self.assertIn("Price should not be provided for MARKET orders", str(ctx.exception))

    def test_validate_stop_price(self):
        # STOP_MARKET requires stop price
        self.assertEqual(validate_stop_price(60000, "STOP_MARKET"), Decimal("60000"))
        with self.assertRaises(ValueError) as ctx:
            validate_stop_price(None, "STOP_MARKET")
        self.assertIn("Stop price (--stop-price) is required", str(ctx.exception))

        # Other orders do not require stop price
        self.assertIsNone(validate_stop_price(None, "LIMIT"))

    def test_validate_all(self):
        result = validate_all(
            symbol="ethusdt",
            side="buy",
            order_type="limit",
            quantity="0.5",
            price="3500.50"
        )
        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["side"], "BUY")
        self.assertEqual(result["order_type"], "LIMIT")
        self.assertEqual(result["quantity"], Decimal("0.5"))
        self.assertEqual(result["price"], Decimal("3500.50"))
        self.assertIsNone(result["stop_price"])


class TestBinanceClient(unittest.TestCase):
    """Verify HMAC signature generation and client request behaviors."""

    def setUp(self):
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        self.client = BinanceClient(api_key=self.api_key, api_secret=self.api_secret)

    def test_signature_generation(self):
        # The SHA256 HMAC for the query string below using "test_secret" key
        params = {"symbol": "LTCUSDT", "side": "BUY", "timestamp": 1600000000000}
        sig = self.client._sign(params)
        self.assertEqual(len(sig), 64)  # Hex digest length
        # Check that it produces hexadecimal output
        int(sig, 16)

    def test_build_signed_params(self):
        params = {"symbol": "BTCUSDT"}
        signed = self.client._build_signed_params(params)
        self.assertIn("timestamp", signed)
        self.assertIn("recvWindow", signed)
        self.assertIn("signature", signed)
        self.assertEqual(signed["recvWindow"], 5000)

    @patch("requests.Session.get")
    def test_get_exchange_info(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"timezone": "UTC", "serverTime": 1700000000000}
        mock_get.return_value = mock_resp

        result = self.client.get_exchange_info()
        self.assertEqual(result["timezone"], "UTC")
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_api_error_handling(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": -1102, "msg": "Mandatory parameter 'interval' was not sent, is empty, or malformed."}
        mock_get.return_value = mock_resp

        with self.assertRaises(BinanceAPIError) as ctx:
            self.client.get_account()
        
        self.assertEqual(ctx.exception.code, -1102)
        self.assertIn("Mandatory parameter", ctx.exception.message)


class TestOrders(unittest.TestCase):
    """Verify order dispatching and result display formatting."""

    def test_order_result_display(self):
        raw_payload = {
            "orderId": 1234567,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "status": "FILLED",
            "clientOrderId": "test_client_id",
            "origQty": "0.005",
            "executedQty": "0.005",
            "avgPrice": "68500.00",
        }
        res = OrderResult(raw_payload)
        display = res.display()
        self.assertIn("Order ID       : 1234567", display)
        self.assertIn("Symbol         : BTCUSDT", display)
        self.assertIn("Avg Fill Price : 68500.00", display)

    def test_order_result_display_limit(self):
        raw_payload = {
            "orderId": 987654,
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "status": "NEW",
            "price": "3500.00",
            "origQty": "1.2",
            "executedQty": "0",
            "timeInForce": "GTC",
        }
        res = OrderResult(raw_payload)
        display = res.display()
        self.assertIn("Limit Price    : 3500.00", display)
        self.assertIn("Time-in-Force  : GTC", display)

    @patch("bot.client.BinanceClient.place_order")
    def test_dispatch_order_market(self, mock_place):
        mock_client = BinanceClient("key", "secret")
        mock_place.return_value = {
            "orderId": 123,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "status": "FILLED",
        }
        res = dispatch_order(mock_client, "BTCUSDT", "BUY", "MARKET", Decimal("0.01"))
        self.assertEqual(res.order_id, 123)
        self.assertEqual(res.status, "FILLED")
        mock_place.assert_called_once()


class TestCLI(unittest.TestCase):
    """Verify that CLI handlers route commands and parse arguments correctly."""

    def test_parser_rules(self):
        parser = build_parser()
        
        # Test place arguments
        args = parser.parse_args(["place", "--symbol", "BTCUSDT", "--side", "BUY", "--type", "MARKET", "--qty", "0.05"])
        self.assertEqual(args.command, "place")
        self.assertEqual(args.symbol, "BTCUSDT")
        self.assertEqual(args.side, "BUY")
        self.assertEqual(args.type, "MARKET")
        self.assertEqual(args.qty, 0.05)

        # Test account arguments
        args = parser.parse_args(["account"])
        self.assertEqual(args.command, "account")

    @patch("cli._get_client")
    @patch("cli.dispatch_order")
    def test_cmd_place(self, mock_dispatch, mock_get_client):
        # Setup mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_res = MagicMock()
        mock_res.display.return_value = "Formatted Confirmation Output"
        mock_res.order_id = 999
        mock_res.status = "NEW"
        mock_dispatch.return_value = mock_res

        # Build args
        parser = build_parser()
        args = parser.parse_args([
            "place", "--symbol", "BTCUSDT", "--side", "BUY", "--type", "LIMIT",
            "--qty", "0.005", "--price", "64000.0"
        ])

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            cmd_place(args)
            
            # Assert execution
            mock_get_client.assert_called_once()
            mock_dispatch.assert_called_once_with(
                client=mock_client,
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=Decimal("0.005"),
                price=Decimal("64000.0"),
                stop_price=None,
                time_in_force="GTC"
            )
            
            # Check print statements
            stdout_calls = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
            self.assertIn("ORDER REQUEST SUMMARY", stdout_calls)
            self.assertIn("Formatted Confirmation Output", stdout_calls)
            self.assertIn("Order submitted successfully", stdout_calls)

    @patch("cli._get_client")
    def test_cmd_account(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_account.return_value = {
            "canTrade": True,
            "totalWalletBalance": "12345.67",
            "availableBalance": "9876.54",
            "totalUnrealizedProfit": "120.30"
        }
        mock_get_client.return_value = mock_client

        parser = build_parser()
        args = parser.parse_args(["account"])

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            cmd_account(args)
            
            mock_client.get_account.assert_called_once()
            stdout_calls = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
            self.assertIn("ACCOUNT INFORMATION", stdout_calls)
            self.assertIn("Can Trade  : True", stdout_calls)
            self.assertIn("Total WB   : 12345.67 USDT", stdout_calls)
            self.assertIn("Avail Bal  : 9876.54 USDT", stdout_calls)
            self.assertIn("Unrealised : 120.30 USDT", stdout_calls)

    @patch("cli._get_client")
    def test_cmd_open_orders(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_open_orders.return_value = [
            {
                "orderId": 111,
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "LIMIT",
                "origQty": "0.001",
                "price": "69000.00",
                "status": "NEW"
            }
        ]
        mock_get_client.return_value = mock_client

        parser = build_parser()
        args = parser.parse_args(["orders", "--symbol", "BTCUSDT"])

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            cmd_open_orders(args)
            
            mock_client.get_open_orders.assert_called_once_with(symbol="BTCUSDT")
            stdout_calls = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
            self.assertIn("OPEN ORDERS – BTCUSDT", stdout_calls)
            self.assertIn("[111] BTCUSDT SELL LIMIT qty=0.001 price=69000.00 status=NEW", stdout_calls)


if __name__ == "__main__":
    unittest.main()
