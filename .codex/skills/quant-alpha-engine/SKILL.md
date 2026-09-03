---
name: quant-alpha-engine
description: Build, explain, test, audit, or operate shokodata/quant-alpha-engine, the automated S&P 500 intraday pairs-research engine. Use for its cointegration and OU analytics, catalyst checks, Discord alerts, immutable forward signal ledger, hourly sweep, or weekly validation report; do not treat its signals or estimated returns as validated live-trading instructions.
---

# Quant Alpha Engine

Work from the current `shokodata/quant-alpha-engine` checkout when available. Inspect the repository before changing it; the code and checked-in configuration are authoritative when they differ from this skill.

This system is a research and forward-observation engine, not an order router. Preserve that boundary in implementation, documentation, reports, and recommendations. Never imply that a qualifying pair is safe to trade or that unresolved observations prove an edge.

## Route the request

- For repository orientation, supported commands, input/output contracts, or component ownership, read [references/repository-guide.md](references/repository-guide.md).
- For pair qualification, spread calculations, signal tracking, or result interpretation, also read [references/research-invariants.md](references/research-invariants.md).
- For Yahoo data, Discord, scheduling, ledger commits, or GitHub Actions work, also read [references/automation-and-data.md](references/automation-and-data.md).

## Working method

1. Confirm the active checkout and read its `README.md`, relevant implementation files, tests, and configuration before acting. Do not assume the GitHub default branch matches a local working tree.
2. Distinguish the pair-selection engine, forward tracker, hourly sweep, and weekly validation report. They have different responsibilities and evidence semantics.
3. Keep research claims tied to observable evidence. State the sample, universe, cost assumption, market timestamp, observation count, resolution status, and data limitations when interpreting results.
4. Preserve existing user changes. Treat `signal_ledger.json` as intentional cumulative research state: retain stable signal IDs and existing observations, avoid duplicate open signals, and never rewrite history to improve results.
5. Make the smallest coherent change and test meaningful behavior. This repository may not have a formal test suite; use isolated temporary ledgers through `SIGNAL_LEDGER_PATH` and mock network/Discord calls when verifying ledger or reporting changes.
6. If network data, Discord, GitHub secrets, or scheduled workflows are involved, separate local verification from external effects and obtain any required authorization before posting messages, changing secrets, triggering workflows, or enabling live automation.

## Financial-safety boundary

Treat generated pairs as research observations. A signal is successful only under the ledger's recorded resolution rule; open signals are unresolved. Estimated spread returns use simplified prices, fixed beta, and a cost assumption rather than executable fills. Before any move beyond observation-only research, require genuinely out-of-sample evidence, point-in-time constituents, quote-based fills, liquidity/news/earnings/borrow controls, portfolio risk limits, kill switches, and broker paper trading.
