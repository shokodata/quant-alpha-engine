"""Send the weekly Alpha Quant forward-validation summary to Discord."""
import json
import os
import urllib.request

import pandas as pd

from signal_validation import _load

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def pct(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1%}"


def build_report():
    signals = _load().get("signals", [])
    if not signals:
        return "📊 **ALPHA QUANT — WEEKLY VALIDATION**\n\nNo forward-validation signals have been recorded yet."

    df = pd.DataFrame(signals)
    resolved = df[df["status"] != "OPEN"].copy()
    lines = [
        "📊 **ALPHA QUANT — WEEKLY VALIDATION**",
        "",
        f"**Forward signals:** {len(df)}",
        f"**Open:** {(df['status'] == 'OPEN').sum()}",
        f"**Resolved:** {len(resolved)}",
    ]

    if resolved.empty:
        lines += ["", "Forward tracking is active; no signals have resolved yet."]
        return "\n".join(lines)

    resolved["success"] = resolved["status"].eq("CONVERGED")
    lines += [
        f"**Converged:** {resolved['success'].sum()}",
        f"**Convergence rate:** {pct(resolved['success'].mean())}",
        "",
        f"**Avg terminal return (net est.):** {pct(resolved['latest_pair_return'].mean())}",
        f"**Avg MFE:** {pct(resolved['max_favorable_return'].mean())}",
        f"**Avg MAE:** {pct(resolved['max_adverse_return'].mean())}",
    ]

    if "catalyst_present" in resolved:
        lines += ["", "**Catalyst split**"]
        for flag, group in resolved.groupby("catalyst_present"):
            label = "Catalyst present" if flag else "No detected catalyst"
            lines.append(f"• {label}: {pct(group['success'].mean())} convergence ({len(group)} signals)")

    if resolved["entry_z_reported"].notna().any():
        abs_z = resolved["entry_z_reported"].abs()
        high = resolved[abs_z >= 3.0]
        normal = resolved[(abs_z >= 2.3) & (abs_z < 3.0)]
        lines += ["", "**Entry |Z|**"]
        if len(high):
            lines.append(f"• ≥3.0: {pct(high['success'].mean())} convergence ({len(high)})")
        if len(normal):
            lines.append(f"• 2.3–3.0: {pct(normal['success'].mean())} convergence ({len(normal)})")

    if resolved["half_life_days"].notna().any():
        fast = resolved[resolved["half_life_days"] <= 2.0]
        slow = resolved[resolved["half_life_days"] > 2.0]
        lines += ["", "**Half-life**"]
        if len(fast):
            lines.append(f"• ≤2 days: {pct(fast['success'].mean())} convergence ({len(fast)})")
        if len(slow):
            lines.append(f"• >2 days: {pct(slow['success'].mean())} convergence ({len(slow)})")

    lines += ["", "_Forward results include all recorded qualifying signals; returns are estimated and include the model's transaction-cost assumption._"]
    return "\n".join(lines)


def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not configured")
    payload = {"username": "Quant Alpha Validation", "content": message}
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def main():
    report = build_report()
    print(report)
    send_discord(report)


if __name__ == "__main__":
    main()
