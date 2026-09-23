# Query trace — proving discovery is real (a tool call from server two)

Run: `PYTHONUTF8=1 .venv/Scripts/python.exe -m scripts.run_mcp_agent --claim-number CLM-2027-00201`

```
Connected to servers: ['policy-tools', 'claims-system']
Discovered tools: {'get_claim': 'policy-tools', 'search_policy_text': 'policy-tools',
'compute_claim_payout': 'policy-tools', 'check_policy_claim_history': 'policy-tools',
'submit_decision': 'policy-tools', 'flag_for_review': 'policy-tools',
'get_claim_status': 'claims-system', 'get_adjuster_note_history': 'claims-system'}

status=None payout=None flagged=False

Tool call trace (name, owning server):
  [policy-tools] get_claim({'claim_number': 'CLM-2027-00201'})
  [claims-system] get_claim_status({'claim_number': 'CLM-2027-00201'})
  [claims-system] get_adjuster_note_history({'claim_number': 'CLM-2027-00201'})
  [policy-tools] search_policy_text({'query': 'engine seized flooded street water ingress
    hydrostatic lock Engine Gearbox Protection IMT-29'})

Full log:
iter 1: get_claim({'claim_number': 'CLM-2027-00201'}) -> {"claim_number": "CLM-2027-00201",
  "policy_id": "MOTOR-COMP-01", "sum_insured": 500000, "excess_amount": 1000,
  "claimed_amount": 45000, "adjuster_notes": "Insured's car engine seized after being driven
  through a flooded street during heavy rain. No Engine & Gearbox Protection endorsement on
  file."}
iter 1: get_claim_status({'claim_number': 'CLM-2027-00201'}) -> {"claim_number":
  "CLM-2027-00201", "status": "denied"}
iter 1: get_adjuster_note_history({'claim_number': 'CLM-2027-00201'}) -> {"claim_number":
  "CLM-2027-00201", "notes": [{"date": "2027-01-05", "author": "R. Iyer", "note": "Initial
  review opened. Requesting workshop diagnostic report for engine seizure."},
  {"date": "2027-01-08", "author": "R. Iyer", "note": "No Engine & Gearbox Protection
  endorsement (IMT-29) found on poli...
iter 2: search_policy_text({'query': 'engine seized flooded street water ingress hydrostatic
  lock Engine Gearbox Protection IMT-29'}) -> {"result": [{"source":
  "endorsements_and_riders.md", "chunk_index": 1, "text": "damage due to water ingression,
  mechanical/electrical failure, tyres and tubes (unless the vehicle is also damaged in the
  same accident). ### IMT-29 - Engine & Gearbox Protection\n- **What it does:** Covers
  damag...
BUDGET EXCEEDED before iteration 3: budget exceeded: max_wall_clock_seconds (107.6s > 90.0s)
```

## Reading this honestly

The run followed the exact instruction in the system prompt ("check the claim's current
processing status in the claims-processing system before you finalize") - it called
`get_claim` from `policy-tools`, then immediately called both `claims-system` tools
(`get_claim_status`, `get_adjuster_note_history`) before moving on to `search_policy_text`.
Both server-two tools were called by name, discovered - not hard-coded - proving requirement
1 (server two, tool name shown in trace).

The run itself didn't reach `submit_decision` this time - reranker model load plus three
tool round-trips plus a Gemini call pushed it past the 90s wall-clock budget on this
memory-constrained machine before a fourth model turn could run. That's a budget/latency
outcome, not a discovery failure - the tool call trace above is the actual evidence
requirement 1 asks for, independent of whether the claim was fully triaged in this run.
