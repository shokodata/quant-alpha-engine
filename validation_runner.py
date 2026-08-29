"""Run Alpha Quant unchanged while capturing and updating validation outcomes."""
import runpy

import signal_validation


def main():
    # First advance previously-recorded signals using the newest hourly bar.
    signal_validation.update_open_signals()

    # Patch only the outbound alert function. Every alert that the existing
    # engine independently qualifies is written to the immutable signal ledger
    # before the original Discord delivery executes.
    import alpha_engine
    original_dispatch = alpha_engine.dispatch_discord_alert

    def tracked_dispatch(data):
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


if __name__ == "__main__":
    main()
