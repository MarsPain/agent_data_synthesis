# Domain Glossary

This glossary defines the repository's canonical domain language. It describes
terms, not package structure, implementation plans, or work status. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the system map and
[docs/DESIGN.md](docs/DESIGN.md) for detailed contracts.

## Core Terms

- **Candidate task:** A proposed agent task together with the intent, policy
  hints, expected outcome, and expected state needed to execute and verify it.
- **Domain pack:** A domain-owned bundle of environment construction, tools,
  task semantics, generation policy, verification behavior, and runtime
  metadata. Contacts, mobile messages, and workspace tasks are the current
  deterministic domain packs.
- **Environment:** Executable, isolated state against which tools run. An
  environment is rebuilt per candidate when isolation is required.
- **Tool:** A typed operation over an environment, with a declared input schema
  and deterministic result contract for local fixture paths.
- **Trajectory:** The ordered actions, observations, state transitions, and
  final response produced while attempting a candidate task.
- **Episode:** Sanitized runtime evidence for one task execution, suitable for
  replay, quality scoring, and reward-label derivation.
- **Verifier:** An independent check that compares execution evidence and final
  state with the candidate's declared expected outcome.
- **Accepted sample:** A candidate whose contracts, execution, final answer,
  expected state, and quality gates all pass. Generation alone does not make a
  candidate an accepted sample.
- **Rejection:** A candidate that fails generation, contract, execution,
  verification, grounding, or quality admission, recorded with a bounded reason.

## Run and Release Terms

- **Run profile:** Versioned input that selects a domain, generation mode,
  candidate target, purpose, feature flags, and optional governed source.
- **Diagnostic run:** A run intended to test behavior or collect evidence; it is
  not eligible to establish dataset release readiness.
- **Representative run:** A run that satisfies declared scale, provenance, and
  generation-policy requirements for cross-domain evidence. Representative does
  not mean releaseable.
- **Release candidate:** A profile and artifact set evaluated against explicit
  coverage, quality, provenance, and reproducibility gates.
- **Dataset release pack:** A hash-locked collection of admitted dataset
  artifacts that can be verified without rerunning generation.
- **Source admission:** The policy decision that allows a governed source bundle
  to affect an environment after provenance, license, path or network, size, and
  sandbox checks pass.
- **Lineage:** Sanitized metadata connecting a sample or report to its source,
  profile, provider role, environment, tool, and verification evidence without
  exposing secrets or raw private payloads.
