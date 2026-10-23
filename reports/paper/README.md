# Paper-trading assistant ("المساعد")

Paper only. No broker order endpoint is ever called. Spec: `prompts/PROMPT_TRADE_ASSISTANT.md`.

| What | Where |
|---|---|
| Signals (Python twin of the indicator) | `vzones/assistant/signals.py` |
| Simulator (fixed exit rules) + context | `vzones/assistant/sim.py` |
| Journal (SQLite, WAL) | `runtime/paper.db` via `vzones/assistant/journal.py` |
| Learning + verdicts | `vzones/assistant/learn.py`, frozen split in `runtime/learn_state.json` |
| Live agent (logon task `PaperAgent`) | `tools/paper_agent.py`, log `runtime/paper_agent.log` |
| Assistant page (refreshes every minute) | `runtime/paper_view.html` |
| Parity vs TradingView | `tools/paper_parity.py` -> `parity.txt` |
| History replay | `tools/paper_replay.py` |
| History verdict / daily report / graveyard | `history_verdict.md`, `YYYY-MM-DD.md`, `graveyard.md` |

Data: Alpaca IEX 5-minute bars (split-adjusted) in `runtime/bars/`, Yahoo official daily bars for the whale ranges,
GEXRadar `daily_levels` (previous market date's row = levels known before the open), Yahoo VIX (previous close).
The IEX bars are not TradingView's BATS bars, so live signals can differ from the chart on some bars; parity is
measured on TradingView's own bars, which tests the logic, not the data.
