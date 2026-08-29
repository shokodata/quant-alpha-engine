"""Run Alpha Quant unchanged while capturing and updating validation outcomes."""
import datetime
import json
import logging
import os
import urllib.request
from zoneinfo import ZoneInfo

import signal_validation


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


def main():
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
        signal_validation.record_signal(data)
        original_dispatch(data)

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
    exec(compile(source, "alpha_engine.py", "exec"), namespace, namespace)

    print("VALIDATION SUMMARY:", signal_validation.build_summary())
    _dispatch_sweep_heartbeat(signal_count)


if __name__ == "__main__":
    main()
