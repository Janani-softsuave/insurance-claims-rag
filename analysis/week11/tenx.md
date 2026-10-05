At 10x today's claim volume, the **rate limit** breaks first — and it isn't close. This
project's Gemini free-tier key is capped at `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
= **20 requests/day**, confirmed directly: building and racing Weeks 10-11 against this exact
cap took multiple real days of hourly wait-and-retry cycles to push through roughly 30-40 total
calls, because every day's 20 ran out within hours of being used. ClaimsWorkflow costs exactly
one Gemini call per claim, so today's volume is already bounded near 20 claims/day before the
account's own daily quota halts it; 10x that volume (≈200 claims/day) would exhaust the day's
entire allowance by roughly the 20th claim and leave the other ~180 claims that day unprocessable
— not slow, not expensive, simply refused with a 429. Cost is nowhere near binding at 10x: 200
claims/day × $0.00015967/claim ≈ **$0.032/day**, trivial. Latency is nowhere near binding either:
200 sequential ~10.9s calls ≈ 36 minutes of total compute, easily parallelizable. The rate limit
is the wall; it arrives at claim 20, not claim 200.
