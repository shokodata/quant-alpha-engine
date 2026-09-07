import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import alpha_engine
import validation_runner


class DiscordDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.alert = {
            "Action State": "LONG SPREAD",
            "Beta": 1.1,
            "Catalyst Context": "No flagged catalyst",
            "Cointegration P-Value": 0.01,
            "Current Intraday Z-Score": -2.5,
            "Half-Life Days": 2.0,
            "Historical Sharpe Ratio": 1.2,
            "Pair Name": "AAA vs BBB",
            "Price A": 100.0,
            "Price B": 50.0,
            "Stock A": "AAA",
            "Stock B": "BBB",
            "Sub-Industry": "Test",
        }

    def test_dispatch_reports_only_confirmed_discord_success(self):
        response = mock.MagicMock()
        response.status = 204
        context = mock.MagicMock()
        context.__enter__.return_value = response
        with mock.patch.object(alpha_engine, "DISCORD_WEBHOOK_URL", "https://example.test"), mock.patch(
            "alpha_engine.urllib.request.urlopen", return_value=context
        ):
            self.assertIs(alpha_engine.dispatch_discord_alert(self.alert), True)

    def test_dispatch_reports_failure_when_discord_raises(self):
        with mock.patch.object(alpha_engine, "DISCORD_WEBHOOK_URL", "https://example.test"), mock.patch(
            "alpha_engine.urllib.request.urlopen", side_effect=OSError("offline")
        ):
            self.assertIs(alpha_engine.dispatch_discord_alert(self.alert), False)


class AlphaCastHandoffTests(unittest.TestCase):
    def test_mixed_delivery_run_exposes_only_confirmed_success(self):
        run_time = "2026-09-07T12:00:00+00:00"
        first = {
            "Stock A": "AAA",
            "Stock B": "BBB",
            "Action State": "SHORT SPREAD",
            "Current Intraday Z-Score": 2.6,
            "Beta": 0.4,
            "Cointegration P-Value": 0.012,
            "Historical Sharpe Ratio": 1.4,
            "Half-Life Days": 3.2,
            "Price A": 35.1,
            "Price B": 105.9,
            "Catalyst Context": "No detected catalyst",
        }
        second = {
            "Stock A": "CCC",
            "Stock B": "DDD",
            "Action State": "LONG SPREAD",
        }
        deliveries = []
        dispatcher = mock.Mock(side_effect=[True, False])
        with mock.patch.object(
            validation_runner.signal_validation, "record_signal"
        ) as record_signal, mock.patch.object(
            validation_runner.signal_validation,
            "signal_identity",
            side_effect=[
                {"signal_id": "signal-1", "market_timestamp": "bar-1"},
                {"signal_id": "signal-2", "market_timestamp": "bar-2"},
            ],
        ):
            validation_runner._dispatch_and_capture(
                first, dispatcher, run_time, deliveries
            )
            validation_runner._dispatch_and_capture(
                second, dispatcher, run_time, deliveries
            )

        self.assertEqual(record_signal.call_count, 2)
        self.assertEqual([item["signal_id"] for item in deliveries], ["signal-1"])
        self.assertEqual(deliveries[0]["delivery_status"], "delivered")
        self.assertEqual(deliveries[0]["entry_z"], 2.6)
        self.assertEqual(deliveries[0]["p_value"], 0.012)
        self.assertEqual(deliveries[0]["half_life_days"], 3.2)

    def test_atomic_handoff_contains_exact_successful_delivery_fields(self):
        alert = {
            "workflow_run_time": "2026-09-07T12:00:00+00:00",
            "market_timestamp": "2026-09-07T11:30:00-04:00",
            "signal_id": "signal-1",
            "Stock A": "AAA",
            "Stock B": "BBB",
            "action": "SHORT SPREAD",
            "delivery_status": "delivered",
            "entry_z": 2.6,
            "beta": 0.4,
            "p_value": 0.012,
            "historical_sharpe": 1.4,
            "half_life_days": 3.2,
            "price_a": 35.1,
            "price_b": 105.9,
            "catalyst_present": False,
            "catalyst_context": "No detected catalyst",
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "latest_discord_dispatch.json"
            target.write_text('{"stale": true}\n', encoding="utf-8")
            with mock.patch.object(validation_runner, "DISPATCH_PATH", target):
                validation_runner._write_latest_discord_dispatch(
                    alert["workflow_run_time"], [alert]
                )

            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {
                    "workflow_run_time": alert["workflow_run_time"],
                    "alerts": [alert],
                },
            )
            self.assertEqual(
                set(alert),
                {
                    "workflow_run_time",
                    "market_timestamp",
                    "signal_id",
                    "Stock A",
                    "Stock B",
                    "action",
                    "delivery_status",
                    "entry_z",
                    "beta",
                    "p_value",
                    "historical_sharpe",
                    "half_life_days",
                    "price_a",
                    "price_b",
                    "catalyst_present",
                    "catalyst_context",
                },
            )
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_empty_run_replaces_previous_alerts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "latest_discord_dispatch.json"
            target.write_text('{"alerts": [{"signal_id": "old"}]}\n')
            with mock.patch.object(validation_runner, "DISPATCH_PATH", target):
                validation_runner._write_latest_discord_dispatch(
                    "2026-09-07T13:00:00+00:00", []
                )
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                {
                    "workflow_run_time": "2026-09-07T13:00:00+00:00",
                    "alerts": [],
                },
            )


if __name__ == "__main__":
    unittest.main()
