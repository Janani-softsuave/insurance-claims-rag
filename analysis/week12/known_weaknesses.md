# Top 3 known weaknesses — written before the eval suite ran

1. **The corpus is a thin slice, not the real ~60-page dual policy wordings.** Only the flood
   exclusion got genuinely dated 2023/2025 versions (two small, explicitly-labelled documents).
   Everything else in the corpus is treated as date-agnostic. If the real corpus has other
   clauses that changed between endorsement versions (sub-limits, DUI exclusions, earthquake
   terms), this system has no mechanism to catch those — it will silently retrieve whatever's
   in the corpus with no date conflict warning, because there is no second dated version to
   conflict with. The loss-date filter is real and code-enforced for the one clause I gave it
   two versions of; it is not a general guarantee for the whole corpus.

2. **The "never say covered" guard is a word match on one field, not a semantic check.** The
   MCP server's `refer_to_adjuster` rejects the literal word "covered" (case-insensitive,
   word-boundary) in the `summary` argument. It does nothing to stop the model writing
   "fully payable, no exclusion applies" or "the claimant should expect reimbursement in
   full" — functionally a coverage decision in different words. I expect this to be exactly
   the kind of thing a hostile reviewer finds in five minutes, and I'm naming it before they
   do rather than after.

3. **Trace-id propagation depends on the model faithfully copying a string forward.** The
   `trace_id` crossing the agent/MCP boundary is not enforced by the protocol — it's a
   convention the system prompt asks the model to follow (copy `get_claim`'s returned
   `trace_id` into every later call). If the model ever invents its own value, misreads it, or
   skips it on one call, that one tool's span silently loses its place in the end-to-end
   trace — there is no server-side check that rejects a wrong or missing trace_id, only a
   convention that depends on the model following instructions correctly every time.
