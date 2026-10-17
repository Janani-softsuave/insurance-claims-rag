# Seam list — unedited, as found while integrating

Each seam is marked **fixed**, **accepted**, or **ran-out-of-time**.

1. **Gemini's `FunctionDeclaration` rejects JSON Schema union types.** `"type": ["number",
   "null"]` for an optional `sub_limit` parameter raised a pydantic validation error at
   startup — Gemini's tool schema only accepts a single scalar type. **Fixed**: dropped the
   union, made `sub_limit` a plain `"number"` property that's simply omitted from `required`
   and given a Python default of `None`, with the tool description telling the model to omit
   it when no sub-limit applies.

2. **Chroma's `$lte`/`$gte` where-operators reject string operands**, even ISO date strings
   that would sort correctly as strings. The first version of the date filter used
   `effective_from`/`effective_to` as `"2023-01-01"` strings and Chroma raised `ValueError:
   Expected operand value to be an int or a float`. **Fixed**: store `effective_from_int`/
   `effective_to_int` as `YYYYMMDD` integers alongside the human-readable strings, convert
   `loss_date` the same way at query time. Verified against the exact boundary case
   (2024-12-31 vs 2025-01-01) after the fix — see `trace.json`.

3. **A single-`@app.command()` Typer app silently stops accepting a subcommand name.**
   `python -m scripts.run_capstone triage CLM-2027-00310` failed with "unexpected extra
   argument" — Typer collapses to no-subcommand mode when there's only one command
   registered, a pattern that bit the Week 10 and Week 11 race scripts too. **Accepted**: this
   is now a known quirk of this codebase's CLI pattern; the README states the correct
   invocation (`python -m scripts.run_capstone CLM-2027-00310`, no verb) rather than fixing
   Typer's behavior.

4. **My own diagnostic `grep -v "WARNING"` filter hid the exact signal I needed.** The first
   end-to-end run appeared to hang — zero CPU movement for 15+ seconds looked like a stdio
   deadlock between the agent and the MCP server subprocess. It was not a deadlock: the
   Gemini key-rotation client was silently retrying through a 429, and I had filtered
   `WARNING`-level log lines out of my own test command, so the one line that would have told
   me what was actually happening never reached me. **Fixed** by re-running without the
   filter; logged here because it's a real integration-debugging lesson, not just a line of
   code — the log line that costs you time is sometimes the one you filtered out yourself.

5. **Threading one trace id across a process boundary (agent <-> MCP server) needed a
   deliberate protocol decision, not an afterthought.** The two processes share no memory and
   only exchange whatever the MCP tool schema carries. **Fixed**: `get_claim` mints the
   trace_id and returns it as an ordinary field in its JSON result (which the model sees in
   its own context and is instructed to copy forward as an explicit `trace_id` argument on
   every later tool call); both the agent process (generation spans) and the MCP server
   process (tool-call spans) append to the same flat `analysis/week12/spans.jsonl`, keyed by
   that shared id. No shared memory, no sidecar process, just a convention both sides honor.

6. **`MCPAgent`'s existing terminal-result fields (`status`/`payout`/`rationale`) assumed the
   Week 7/9 claims-decision shape and don't fit a referral-only result.** **Fixed**: added a
   `final: dict` field carrying the raw tool result alongside the existing named fields (kept
   for Week 9 backward compatibility, now best-effort `.get()` lookups that simply return
   `None` for a shape that doesn't have them).

7b. **The agent's wall-clock budget (`max_wall_clock_seconds`) was being blown by retry-wait
    time, not real work, before a single eval claim ever completed.** `BudgetTracker` measures
    elapsed time since the run started; the Gemini key-rotation client's retry backoff
    (including the hourly wait when the model returns persistent 503s or the daily quota is
    hit) happens *inside* one `generate()` call, so the *next* loop iteration's budget check
    sees that whole wait baked into "elapsed seconds" and terminates the claim via
    `BudgetExceeded` before it ever reaches `refer_to_adjuster` — the exact same failure mode
    Week 10's single-agent arm hit (see that week's verdict.md). With a 150s budget and
    multi-hour retry cycles, every claim in the first several hours of this batch run was
    getting silently cut off mid-task. **Fixed**: raised `max_wall_clock_seconds` to a
    practically-unlimited value for this batch run — `max_iterations`/`max_tokens`/
    `max_cost_usd` still bound genuine runaway loops, since none of those are inflated by
    retry-sleep time the way wall-clock is.

7. **The policy corpus never had a flood exclusion at all before this week — "flood" was
   listed as COVERED under the base policy overview, with no exclusion schedule.** The whole
   premise (2023 vs 2025 wording disagreeing on flood) requires an exclusion that changes
   over time to exist in the first place. **Accepted, disclosed as synthetic**: added two
   small, explicitly-dated exclusion-schedule documents rather than rewriting the ~60-page
   corpus the brief says not to touch — the two new files are the only net-new corpus content,
   everything else is the existing Week 3-11 material reused as-is.
