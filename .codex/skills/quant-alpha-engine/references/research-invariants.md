# Research invariants

Read the current engine alongside these invariants before modifying modeling or timing behavior.

## Pair and signal model

- Pair candidates come from stocks sharing a current S&P 500 sub-industry classification. This is current-constituent research, not a point-in-time historical universe.
- Preserve the engine's multi-window cointegration, OU half-life, historical profile, intraday z-score, and catalyst checks when changing qualification logic. Read the exact current thresholds from `alpha_engine.py`; do not copy stale values into the skill.
- A `LONG SPREAD` signal benefits from convergence after a negative spread dislocation; `SHORT SPREAD` is the opposite. Preserve the stock ordering and beta used at entry.
- Record every independently qualifying outbound alert before Discord delivery. Discord failure must not erase or silently change a qualifying research observation.
- Prevent a new open duplicate with the same sorted pair and action while retaining prior resolved history.

## Forward tracking

- Keep the entry beta fixed when recomputing the tracked spread and z-score.
- Add at most one observation per new market timestamp. Do not treat repeated workflow executions over the same completed bar as new evidence.
- Estimate pair return from the recorded entry prices, fixed beta, signal direction, and checked-in round-trip cost assumption.
- Resolve only under the explicit convergence, adverse-z, or maximum-observation rules. Open signals are not wins or losses.
- Maintain stable signal IDs, entry fields, observation history, MFE/MAE, and resolution timestamps. Never revise earlier observations to improve reported performance.
- Use a temporary path through `SIGNAL_LEDGER_PATH` for tests so verification cannot overwrite the production ledger.

## Interpretation

The stored return is a net estimate, not a fill. It omits quote-level spread, impact, partial fills, borrow availability, and execution latency. Report resolved and open counts separately; convergence rate uses resolved signals only. Treat catalyst splits, entry-z groups, and half-life groups as descriptive until sample sizes and out-of-sample evidence are adequate.
