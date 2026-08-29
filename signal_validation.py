import datetime as dt
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

LEDGER_PATH = Path(os.environ.get("SIGNAL_LEDGER_PATH", "signal_ledger.json"))
MAX_OBSERVATIONS = 35          # ~5 US equity trading days at hourly cadence
CONVERGENCE_Z = 0.50
ADVERSE_Z = 4.00
ESTIMATED_ROUND_TRIP_COST = 0.0014


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


def _load():
    if not LEDGER_PATH.exists():
        return {"schema_version": 1, "signals": []}
    try:
        return json.loads(LEDGER_PATH.read_text())
    except Exception:
        return {"schema_version": 1, "signals": []}


def _save(ledger):
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def _safe_float(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _pair_hourly(t1, t2, period="1mo"):
    raw = yf.download(
        [t1, t2], period=period, interval="1h", progress=False,
        group_by="column", threads=False, timeout=30,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        field = "Adj Close" if "Adj Close" in raw.columns.get_level_values(0) else "Close"
        px = raw[field].copy()
    else:
        px = raw[["Adj Close" if "Adj Close" in raw.columns else "Close"]].copy()
        px.columns = [t1]
    if t1 not in px.columns or t2 not in px.columns:
        return pd.DataFrame()
    return px[[t1, t2]].dropna()


def _fixed_beta_z(pair_df, t1, t2, beta, lookback=120):
    if pair_df.empty or len(pair_df) < 12:
        return None, None, None, None
    spreads = pair_df[t1].astype(float) - beta * pair_df[t2].astype(float)
    history = spreads.tail(min(lookback, len(spreads)))
    if len(history) < 12:
        return None, None, None, None
    reference = history.iloc[:-1]
    std = float(reference.std(ddof=0))
    if not math.isfinite(std) or std <= 0:
        return float(history.iloc[-1]), None, float(reference.mean()), None
    mean = float(reference.mean())
    z = float((history.iloc[-1] - mean) / std)
    return float(history.iloc[-1]), z, mean, std


def _has_open_duplicate(signals, t1, t2, action):
    pair_key = "|".join(sorted([t1, t2]))
    for signal in signals:
        if signal.get("status") != "OPEN":
            continue
        if signal.get("pair_key") == pair_key and signal.get("action") == action:
            return True
    return False


def record_signal(data):
    """Persist a fully-qualified live alert without changing strategy decisions."""
    ledger = _load()
    t1, t2 = data["Stock A"], data["Stock B"]
    action = data["Action State"]
    if _has_open_duplicate(ledger["signals"], t1, t2, action):
        return False

    beta = float(data["Beta"])
    px = _pair_hourly(t1, t2)
    spread, recomputed_z, spread_mean, spread_std = _fixed_beta_z(px, t1, t2, beta)
    market_ts = None
    if not px.empty:
        market_ts = pd.Timestamp(px.index[-1]).isoformat()

    now = _utcnow()
    signal_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{t1}-{t2}-{action.split()[0]}"
    catalyst_text = str(data.get("Catalyst Context", ""))
    has_catalyst = "⚠️" in catalyst_text

    signal = {
        "signal_id": signal_id,
        "created_at_utc": now.isoformat(),
        "market_timestamp": market_ts,
        "pair_key": "|".join(sorted([t1, t2])),
        "stock_a": t1,
        "stock_b": t2,
        "sub_industry": data.get("Sub-Industry"),
        "action": action,
        "entry_price_a": _safe_float(data.get("Price A")),
        "entry_price_b": _safe_float(data.get("Price B")),
        "entry_z_reported": _safe_float(data.get("Current Intraday Z-Score")),
        "entry_z_recomputed": _safe_float(recomputed_z),
        "beta": _safe_float(beta),
        "cointegration_p_value": _safe_float(data.get("Cointegration P-Value")),
        "historical_sharpe": _safe_float(data.get("Historical Sharpe Ratio")),
        "half_life_days": _safe_float(data.get("Half-Life Days")),
        "entry_spread": _safe_float(spread),
        "entry_spread_mean": _safe_float(spread_mean),
        "entry_spread_std": _safe_float(spread_std),
        "catalyst_present": has_catalyst,
        "catalyst_context": catalyst_text,
        "status": "OPEN",
        "resolution_reason": None,
        "resolved_at_utc": None,
        "observation_count": 0,
        "last_observed_market_timestamp": market_ts,
        "latest_z": _safe_float(recomputed_z),
        "latest_pair_return": 0.0,
        "max_favorable_return": 0.0,
        "max_adverse_return": 0.0,
        "observations": [],
    }
    ledger["signals"].append(signal)
    _save(ledger)
    return True


def _pair_return(signal, price_a, price_b):
    a0 = signal.get("entry_price_a")
    b0 = signal.get("entry_price_b")
    beta = signal.get("beta")
    if None in (a0, b0, beta) or (abs(a0) + abs(beta * b0)) == 0:
        return None
    spread_pnl = (price_a - a0) - beta * (price_b - b0)
    gross = abs(a0) + abs(beta * b0)
    raw = spread_pnl / gross
    direction = 1.0 if signal["action"] == "LONG SPREAD" else -1.0
    return direction * raw - ESTIMATED_ROUND_TRIP_COST


def update_open_signals():
    """Add one observation per new hourly market timestamp and resolve outcomes."""
    ledger = _load()
    changed = False

    for signal in ledger["signals"]:
        if signal.get("status") != "OPEN":
            continue
        t1, t2 = signal["stock_a"], signal["stock_b"]
        beta = float(signal["beta"])
        try:
            px = _pair_hourly(t1, t2)
            if px.empty:
                continue
            market_ts = pd.Timestamp(px.index[-1]).isoformat()
            if market_ts == signal.get("last_observed_market_timestamp"):
                continue

            spread, z, _, _ = _fixed_beta_z(px, t1, t2, beta)
            if z is None:
                continue
            price_a = float(px[t1].iloc[-1])
            price_b = float(px[t2].iloc[-1])
            pair_ret = _pair_return(signal, price_a, price_b)
            if pair_ret is None:
                continue

            obs = {
                "market_timestamp": market_ts,
                "price_a": price_a,
                "price_b": price_b,
                "spread": _safe_float(spread),
                "z": _safe_float(z),
                "pair_return_net_est": _safe_float(pair_ret),
            }
            signal["observations"].append(obs)
            signal["observation_count"] = int(signal.get("observation_count", 0)) + 1
            signal["last_observed_market_timestamp"] = market_ts
            signal["latest_z"] = _safe_float(z)
            signal["latest_pair_return"] = _safe_float(pair_ret)
            signal["max_favorable_return"] = max(float(signal.get("max_favorable_return", 0.0)), pair_ret)
            signal["max_adverse_return"] = min(float(signal.get("max_adverse_return", 0.0)), pair_ret)

            converged = abs(z) <= CONVERGENCE_Z
            adverse = (
                signal["action"] == "LONG SPREAD" and z <= -ADVERSE_Z
            ) or (
                signal["action"] == "SHORT SPREAD" and z >= ADVERSE_Z
            )
            timed_out = signal["observation_count"] >= MAX_OBSERVATIONS

            if converged:
                signal["status"] = "CONVERGED"
                signal["resolution_reason"] = f"abs(z) <= {CONVERGENCE_Z}"
            elif adverse:
                signal["status"] = "STOPPED"
                signal["resolution_reason"] = f"adverse z >= {ADVERSE_Z}"
            elif timed_out:
                signal["status"] = "TIMEOUT"
                signal["resolution_reason"] = f"no convergence in {MAX_OBSERVATIONS} hourly observations"

            if signal["status"] != "OPEN":
                signal["resolved_at_utc"] = _utcnow().isoformat()
            changed = True
        except Exception as exc:
            signal["last_tracking_error"] = str(exc)[:300]
            changed = True

    if changed:
        _save(ledger)
    return ledger


def build_summary():
    ledger = _load()
    signals = ledger.get("signals", [])
    resolved = [s for s in signals if s.get("status") != "OPEN"]
    converged = [s for s in resolved if s.get("status") == "CONVERGED"]
    summary = {
        "total_signals": len(signals),
        "open_signals": sum(s.get("status") == "OPEN" for s in signals),
        "resolved_signals": len(resolved),
        "converged_signals": len(converged),
        "convergence_rate": (len(converged) / len(resolved)) if resolved else None,
    }
    if resolved:
        returns = [s.get("latest_pair_return") for s in resolved if s.get("latest_pair_return") is not None]
        summary["avg_resolved_return_net_est"] = float(np.mean(returns)) if returns else None
    return summary
