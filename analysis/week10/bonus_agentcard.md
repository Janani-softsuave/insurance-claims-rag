# Bonus — AgentCard and the A2A task lifecycle

## AgentCard the orchestrator would advertise

```json
{
  "name": "claims-triage-orchestrator",
  "description": "Manager agent that triages an insurance claim by delegating to a coverage/exclusions specialist and an adjuster-note summary specialist, then synthesizes a final coverage decision.",
  "url": "https://internal.abc-insurance.example/a2a/claims-triage-orchestrator",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "authentication": {
    "schemes": ["bearer"]
  },
  "skills": [
    {
      "id": "triage-claim",
      "name": "Triage an insurance claim",
      "description": "Given a claim number, fetches the claim record, checks coverage/exclusions and the adjuster's notes via two internal specialists, and returns a claim_status, payout, and rationale, or escalates to a human adjuster.",
      "tags": ["insurance", "claims", "coverage-decision"],
      "examples": ["Triage claim CLM-2027-00206"],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"]
    }
  ]
}
```

This deliberately advertises one skill, not the orchestrator's internal structure — the two
specialist workers are not separately addressable A2A agents here; they are implementation detail
behind the manager's one skill, the same way the gateway in Week 9 hid two MCP servers behind one
`tools/list`. A caller sends a claim number and gets back a decision or an escalation; it does not
need to know a coverage/exclusions worker or a summary worker exists.

## Mapping the injected-failure case onto the A2A task lifecycle

CLM-2027-00206's run (see `failure_case.md`): the exclusions worker failed twice (simulated 500),
the manager did not guess, and it called `flag_for_review` instead of `submit_decision`.

**That task should end at `input-required`, not `failed`.** A2A's `failed` state means the task
cannot be completed and there is no path forward without starting over. That is not what happened
here — the orchestrator's conclusion was specific and actionable: "the exclusions check could not
run; a human adjuster needs to make the coverage call." That is exactly the shape of
`input-required` — the task is paused, not dead, and it can resume to `completed` the moment a
human adjuster supplies the missing input (their coverage decision) back into the task. Ending it
as `failed` would throw away the partial work already done (the claim record was fetched, the
adjuster-note summary succeeded) and would read to the calling system as "retry the whole thing,"
when what actually happened is "one named input is missing, supply it and this finishes."

## What A2A buys over a plain REST call to the worker

A REST call to the exclusions worker gives you an HTTP status code and a response body; the caller
has to invent its own convention for "this didn't error, but it also can't finish without a human"
versus "this is broken, retry later" — and every caller integrating with this service would invent
that convention differently. A2A's task lifecycle (`submitted` → `working` → `input-required` →
`completed`/`failed`) gives that distinction a name every A2A client already understands, so the
claims-processing front end can render "needs adjuster" differently from "system error" without
bespoke parsing — and the AgentCard lets a new caller discover what this agent can do and how to
authenticate before writing any integration code at all, instead of reading undocumented REST
endpoints.
