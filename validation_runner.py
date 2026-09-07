"""Run Alpha Quant unchanged while capturing and updating validation outcomes."""
import datetime
import json
import logging
import os
import tempfile
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import signal_validation


DISPATCH_PATH = Path(
    os.environ.get("LATEST_DISCORD_DISPATCH_PATH", "latest_discord_dispatch.json")
)


def _is_us_market_hours(now=None):
    """Return True during regular U.S. equity market hours, weekdays only."""
    eastern = ZoneInfo("America/New_York")
    now_et = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(eastern)
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def _dispatch_sweep_heartbeat(signal_count):
    """Confirm a completed market-hours sweep even when no pair qualifies."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook or not _is_us_market_hours():
        return

    now_et = datetime.datetime.now(datetime.timezone.utc).astimezone(
        ZoneInfo("America/New_York")
    )
    noun = "signal" if signal_count == 1 else "signals"
    payload = {
        "username": "Quant Alpha Alpha-Force",
        "content": (
            f"✅ Alpha Quant sweep completed — {signal_count} qualifying {noun} "
            f"| {now_et.strftime('%Y-%m-%d %I:%M %p ET')}"
        ),
    }

    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status in (200, 204):
                logging.info("Discord sweep heartbeat delivered.")
    except Exception as err:
        # Heartbeat delivery must never invalidate an otherwise successful sweep.
        logging.error(f"Discord sweep heartbeat delivery failed: {err}")


def _write_latest_discord_dispatch(workflow_run_time, alerts):
    """Atomically replace AlphaCast's read-only view of this sweep's deliveries."""
    if any(alert.get("workflow_run_time") != workflow_run_time for alert in alerts):
        raise ValueError("All handoff alerts must belong to the current workflow run")
    payload = {
        "workflow_run_time": workflow_run_time,
        "alerts": alerts,
    }
    DISPATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DISPATCH_PATH.parent,
            prefix=f".{DISPATCH_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, DISPATCH_PATH)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _dispatch_and_capture(data, original_dispatch, workflow_run_time, alerts):
    """Record every qualification, but expose only confirmed Discord deliveries."""
    signal_validation.record_signal(data)
    identity = signal_validation.signal_identity(data)
    delivered = original_dispatch(data)
    if delivered is not True:
        return False
    if not identity or not identity.get("signal_id"):
        logging.error(
            "Discord alert delivered but no signal ledger identity was found."
        )
        return True
    alerts.append({
        "workflow_run_time": workflow_run_time,
        "market_timestamp": identity.get("market_timestamp"),
        "signal_id": identity["signal_id"],
        "Stock A": data["Stock A"],
        "Stock B": data["Stock B"],
        "action": data["Action State"],
        "delivery_status": "delivered",
        # Snapshot the diagnostics from this exact sweep. The stable signal ID
        # may point at an older OPEN ledger observation when duplicate
        # prevention is active, so AlphaCast must not recover these values from
        # that historical entry.
        "entry_z": _optional_float(data.get("Current Intraday Z-Score")),
        "beta": _optional_float(data.get("Beta")),
        "p_value": _optional_float(data.get("Cointegration P-Value")),
        "historical_sharpe": _optional_float(data.get("Historical Sharpe Ratio")),
        "half_life_days": _optional_float(data.get("Half-Life Days")),
        "price_a": _optional_float(data.get("Price A")),
        "price_b": _optional_float(data.get("Price B")),
        "catalyst_present": "⚠️" in str(data.get("Catalyst Context", "")),
        "catalyst_context": str(data.get("Catalyst Context", "")),
    })
    return True


def _optional_float(value):
    return None if value is None else float(value)


def main():
    workflow_run_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    delivered_alerts = []
    # Establish this run's empty handoff immediately so an early sweep failure
    # can never leave AlphaCast reading successful deliveries from a prior run.
    _write_latest_discord_dispatch(workflow_run_time, delivered_alerts)

    # First advance previously-recorded signals using the newest hourly bar.
    signal_validation.update_open_signals()

    # Patch only the outbound alert function. Every alert that the existing
    # engine independently qualifies is written to the immutable signal ledger
    # before the original Discord delivery executes.
    import alpha_engine
    original_dispatch = alpha_engine.dispatch_discord_alert
    signal_count = 0

    def tracked_dispatch(data):
        nonlocal signal_count
        signal_count += 1
        _dispatch_and_capture(
            data, original_dispatch, workflow_run_time, delivered_alerts
        )

    alpha_engine.dispatch_discord_alert = tracked_dispatch

    # alpha_engine's sweep lives under its __main__ block, so execute its source
    # with the patched dispatch injected into the run namespace.
    source = open("alpha_engine.py", "r", encoding="utf-8").read()
    source = source.replace(
        "def dispatch_discord_alert(data):",
        "def _original_dispatch_discord_alert(data):",
        1,
    )
    namespace = {
        "__name__": "__main__",
        "dispatch_discord_alert": tracked_dispatch,
    }
    try:
        exec(compile(source, "alpha_engine.py", "exec"), namespace, namespace)
    finally:
        _write_latest_discord_dispatch(workflow_run_time, delivered_alerts)

    print("VALIDATION SUMMARY:", signal_validation.build_summary())
    _dispatch_sweep_heartbeat(signal_count)


if __name__ == "__main__":
    main()
