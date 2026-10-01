# Backend

The supported deployment is one local Python process and one run directory.
`main.py` delegates to `agent_synthesis.app`, which composes registered adapters
and calls `SynthesisEngine`. `engine.py` owns the lifecycle; CLI modules only
parse file locations and report sanitized status.

The private SQLite ledger holds operational state and per-role physical-request
accounting. A writer lock prevents concurrent writers to one run directory.
Workers may run bounded Episodes concurrently within that process. A partial or
cancelled run can resume from frozen inputs and persisted terminal outcomes.

The production model boundary is a strict JSON OpenAI-compatible HTTP adapter.
Scripted fixture responses use the same JSON contract for offline tests. The
CLI requires an explicit authorization flag and non-secret authorization ID
before constructing a live provider adapter. No local LLM server or external
workspace service is part of the core.

The three built-in Domain adapters are composed in `builtin_domains.py`; a new
Domain registers through `AdapterRegistry` without a generic engine branch.
There is no release-lab package or synthesis dependency on a dataset consumer.
