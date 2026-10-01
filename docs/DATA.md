# Data and Evidence

A run exports `demonstrations.jsonl`, `negatives.jsonl`, `manifest.json`,
`provider_usage.json`, `quality_report.json`, and `run_report.json` into its
selected directory under `artifacts/`. Private SQLite and frozen snapshots are
operational inputs and are not public dataset records.

Each public Episode binds a run, Domain version, model lineage, public task,
observable action/observation sequence, final response, deterministic
assessment, and structural family. The private semantic key and oracle stay in
the ledger. Collections are sanitized before export; raw prompts, provider
responses, credentials, and source rows are excluded.

The flat manifest binds exported collection hashes and run identity. Replay
writes `replay_report.json` and reports observation or assessment drift without
provider requests. Usage reports separate observed token counts from unknown
usage; missing prices and downstream training benefit are not estimated.

A blind review queue exposes only public task and observable trajectory.
Direct-human labels bind Episode and cohort IDs, contain five rubric dimensions,
and can mark pass, fail, or uncertain with event references. Missing, failed,
and uncertain labels are not human approval. AI diagnostic reviews must use a
different schema and cannot be imported as human labels.

The frozen three-Domain campaign has 120 Episodes. Its AI diagnostic review
records 106 pass, 13 fail, and 1 uncertain, but formal human dataset acceptance
is incomplete. The exact work state and artifact locations are recorded in the
[local tracker](../.scratch/agent-first-core-rebuild/issues/09-run-three-domain-agent-acceptance.md).
Historical legacy data schemas and profiles remain in repository history; the
current core has no compatibility reader.
