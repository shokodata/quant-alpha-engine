# Automation and data

## Hourly workflow

`.github/workflows/hourly_sweep.yml` schedules the Automated Market Engine hourly at minute 17 and supports manual dispatch. It installs fresh analytics dependencies, runs `validation_runner.py`, and commits changed `signal_ledger.json` to `main`.

All sweep runs share one concurrency group with `cancel-in-progress: false`. Keep writers serialized. Because a queued manual event may contain an older head SHA, checkout must explicitly use the latest `main`; otherwise its generated ledger commit can conflict when rebased over the preceding run's ledger commit.

The persistence step runs with `if: always()` so tracking changes made before a strategy error can still be saved. Preserve that recovery behavior. A persistence failure after a successful sweep means the generated observations may not have reached the repository; inspect later ledger commits before assuming recovery.

GitHub scheduled workflows can be delayed or dropped. The minute-17 choice reduces top-of-hour congestion but does not guarantee hourly coverage. Do not add redundant schedules casually: repeated sweeps can increase Yahoo load and Discord noise. If guaranteed cadence becomes necessary, use an independently monitored scheduler with explicit authorization and idempotent dispatch.

`.github/workflows/weekly_validation_report.yml` reads the committed ledger on Saturday and posts a resolved/open summary to Discord.

## Data integrity

- Current S&P 500 membership and sub-industry labels introduce survivorship and classification bias in historical interpretation.
- Yahoo/yfinance is unofficial and may be delayed, incomplete, rate-limited, or inconsistent across interval types.
- Use market timestamps from downloaded bars, not workflow wall-clock time, when judging observation cadence.
- Do not fabricate missing prices or silently change ticker mappings to increase coverage.
- Catalyst scraping is contextual and incomplete; absence of a detected headline is not evidence that no catalyst exists.

## Discord and external effects

Keep webhook values in GitHub Actions secrets, never source files, logs, fixtures, or reports. Formatting can be tested locally without sending. Posting to Discord, triggering a workflow, editing repository secrets, or changing a live schedule is an external effect and requires user authorization when not explicitly requested.

Hourly qualifying alerts, market-hours heartbeats, and weekly reports are external effects. Reports must retain research/estimated-return language and distinguish open from resolved signals. Failures must not expose webhook secrets or raw environment data.
