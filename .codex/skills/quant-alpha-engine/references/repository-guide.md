# Repository guide

## Identity and scope

- Repository: `https://github.com/shokodata/quant-alpha-engine`
- Runtime used by automation: Python 3.10
- Main dependencies: `pandas`, `statsmodels`, `numpy`, `yfinance`, `lxml`, and `html5lib`
- Purpose: S&P 500 same-sub-industry pair discovery, intraday spread qualification, Discord observation alerts, and forward validation

Always consult the current checkout for exact behavior.

## Component map

- `alpha_engine.py`: harvests the current S&P 500 universe, downloads market data, evaluates same-sub-industry pairs, checks cointegration/OU/catalyst context, and dispatches qualifying alerts.
- `validation_runner.py`: advances open signals, runs the existing engine with a tracked Discord dispatcher, records new qualifying alerts, prints the validation summary, and sends a market-hours heartbeat.
- `signal_validation.py`: schema, duplicate prevention, fixed-beta z-score tracking, estimated pair return, resolution rules, and summaries for `signal_ledger.json`.
- `signal_ledger.json`: cumulative forward-observation state committed by automation.
- `validation_report.py`: local text summary of ledger outcomes.
- `weekly_validation_discord.py`: weekly Discord validation report.
- `.github/workflows/hourly_sweep.yml`: hourly market sweep and ledger persistence.
- `.github/workflows/weekly_validation_report.yml`: Saturday validation summary.

## Commands

```sh
python3 validation_runner.py
python3 validation_report.py
python3 weekly_validation_discord.py
```

The first command performs network downloads and may post Discord messages; do not run it during ordinary local verification. The weekly command posts externally when the webhook is configured. Prefer isolated tests of pure functions and a temporary ledger for diagnostics.

The repository currently has no README, packaging metadata, or formal test directory. Do not assume older `residual_alpha` modules or CLI commands still exist.
