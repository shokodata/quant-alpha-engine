"""Summarize forward Alpha Quant signal performance from signal_ledger.json."""
import pandas as pd

from signal_validation import _load


def main():
    signals = _load().get("signals", [])
    if not signals:
        print("No validation signals recorded yet.")
        return

    df = pd.DataFrame(signals)
    print("\nALPHA QUANT FORWARD VALIDATION")
    print("=" * 72)
    print(f"Signals: {len(df)}")
    print(df["status"].value_counts(dropna=False).to_string())

    resolved = df[df["status"] != "OPEN"].copy()
    if resolved.empty:
        print("\nNo resolved signals yet; forward tracking is active.")
        return

    resolved["success"] = resolved["status"].eq("CONVERGED")
    print(f"\nConvergence rate: {resolved['success'].mean():.1%}")
    print(f"Average net estimated terminal return: {resolved['latest_pair_return'].mean():.3%}")
    print(f"Average max favorable excursion: {resolved['max_favorable_return'].mean():.3%}")
    print(f"Average max adverse excursion: {resolved['max_adverse_return'].mean():.3%}")

    print("\nBY CATALYST STATUS")
    catalyst = resolved.groupby("catalyst_present").agg(
        signals=("signal_id", "count"),
        convergence=("success", "mean"),
        avg_return=("latest_pair_return", "mean"),
        avg_mae=("max_adverse_return", "mean"),
        avg_mfe=("max_favorable_return", "mean"),
    )
    print(catalyst.to_string(float_format=lambda x: f"{x:.3f}"))

    if resolved["half_life_days"].notna().any():
        resolved["half_life_bucket"] = pd.cut(
            resolved["half_life_days"],
            bins=[-float("inf"), 2, 4, float("inf")],
            labels=["<=2d", "2-4d", ">4d"],
        )
        print("\nBY HALF-LIFE")
        hl = resolved.groupby("half_life_bucket", observed=True).agg(
            signals=("signal_id", "count"),
            convergence=("success", "mean"),
            avg_return=("latest_pair_return", "mean"),
        )
        print(hl.to_string(float_format=lambda x: f"{x:.3f}"))

    if resolved["entry_z_reported"].notna().any():
        resolved["abs_entry_z"] = resolved["entry_z_reported"].abs()
        resolved["z_bucket"] = pd.cut(
            resolved["abs_entry_z"],
            bins=[0, 2.5, 3.0, 3.5, float("inf")],
            labels=["<2.5", "2.5-3.0", "3.0-3.5", ">=3.5"],
        )
        print("\nBY ENTRY |Z|")
        ztab = resolved.groupby("z_bucket", observed=True).agg(
            signals=("signal_id", "count"),
            convergence=("success", "mean"),
            avg_return=("latest_pair_return", "mean"),
        )
        print(ztab.to_string(float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
