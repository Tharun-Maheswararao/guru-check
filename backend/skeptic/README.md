# Skeptic (Person 2)

**Model:** Gemini 4 Carbon. Reviews the backtest code for lookahead bias, checks the guru's
claims, reads the random trader comparison, gives the verdict and shapes the NPC personality.

Verdicts: `Real Edge`, `Lucky`, `Just the Market`, `Untestable`.

**Auditor (second managed agent, `audit.py`).** Google's Antigravity managed agent on
`gemini-4-carbon`, in its own sandbox. It runs alongside the judge. It gets:
- the strategy code
- recent real candles
- the NPC's reading
- our engine's rules
- our engine's numbers on those same candles

Then it:
1. writes its own backtest and recomputes the final balance, closed trades and max drawdown
2. scrambles prices after three cut points to catch lookahead

A mismatch or lookahead caps the verdict at Lucky. The findings are saved in the NPC record under
`audit`. A failed or slow audit (over 200 seconds) is recorded as unavailable and never blocks a birth.
`AUDIT_AGENT=0` turns it off.
