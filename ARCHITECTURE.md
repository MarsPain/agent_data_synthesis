# Architecture

The public entrypoint is `main.py`; it delegates to `agent_synthesis.app` and
`SynthesisEngine`. The repository has one active synthesis implementation:
`agent_synthesis/`. Canonical contracts live in [docs/DESIGN.md](docs/DESIGN.md),
with historical framework context in
[docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md).
Terms are defined in [CONTEXT.md](CONTEXT.md).

## Package map

- `configuration.py` validates one immutable run configuration, including slot,
  step, retry, and physical-request ceilings.
- `builtin_domains.py` is the only production composition point for Contacts,
  Mobile Messages, and Workspace Tasks. Each Domain adapter owns its source,
  task compilation, isolated state, tools, authorization, and assessment.
- `registry.py` resolves Domain and JSON model adapters without importing
  concrete Domains into the generic engine.
- `engine.py` owns scheduling, deterministic admission, replay, review cohorts,
  cancellation, and frozen-input resume.
- `ledger.py` keeps private SQLite work, request, and terminal-outcome state.
  Public collections and the flat manifest contain only sanitized evidence.
- `model.py` provides strict JSON contracts, a scripted fake, and an
  OpenAI-compatible remote adapter. The CLI requires fresh authorization before
  it configures the remote adapter.
- `quality.py` keeps shadow judgments and direct-human labels separate from
  deterministic admission. `enforcement.py` evaluates an optional frozen judge
  policy; unqualified enforcement does not affect shadow runs.

`artifacts/` holds runtime outputs. `.scratch/` holds current work state.
`docs/` holds canonical design and operational detail. The removed legacy code
and profiles remain available only through repository history.
System-wide decisions are indexed in [docs/adr/README.md](docs/adr/README.md).
