# Define the Specification Artifact Split and Handoff

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define the Workspace Tracer Proof](10-workspace-tracer-proof.md)

## Question

Which resolved decisions belong in the canonical product specification, deep
design document, ADRs, domain glossary, and implementation acceptance plan, and
what exact handoff index preserves a single source of truth without copying the
Wayfinder resolution comments into multiple long-lived documents?

## Resolution comment

Use one product specification, one deep design, two focused ADRs, the existing
domain glossary, and Local Markdown implementation tickets. Do not create a new
execution-plan artifact.

### Canonical artifact ownership

| Artifact | Canonical path | Owns | Does not own |
| --- | --- | --- | --- |
| Product specification | `docs/product-specs/outcome-validated-domain-pack.md` | Desired behavior, scope, actors, qualification claims, evidence requirements, Workspace tracer acceptance, compatibility acceptance, implementation and testing decisions, and change-scoped rollout or verification | Deep interface mechanics, live ticket state, or full decision-history rationale |
| Deep design | `docs/design-docs/outcome-validated-domain-pack.md` | Target `DomainPack` / `DomainRun` structure, typed interfaces, data and evidence flow, identity and version binding, compatibility projections, qualification state machine mechanics, failure modes, and tracer topology | Product acceptance criteria, live delivery status, or duplicated ADR rationale |
| ADR 0002 | `docs/adr/0002-domain-pack-semantic-authority-and-deep-interface.md` | The durable decision that a Domain Pack is both the domain semantic authority and the common deep integration interface, while domains retain different internal implementations | Complete interface or migration design |
| ADR 0003 | `docs/adr/0003-separate-evidence-verification-from-external-authority.md` | The durable boundary that the framework verifies evidence and computes eligibility but does not replace human publication authority or own external model training | Complete publishability or training protocol |
| Domain glossary | `CONTEXT.md` | Canonical terms and concise definitions only | Requirements, architecture, algorithms, or work state |
| Implementation tracker | `.scratch/outcome-validated-domain-pack/README.md` and `issues/` | Work slices, dependency order, assignees, status, ticket-local scope guards, and externally observable acceptance checks derived from the approved spec | A second copy of product requirements or target-system design |

The phrase "implementation acceptance plan" therefore means the combination of
canonical acceptance requirements in the product spec and checked acceptance
criteria in implementation tickets. It is not a new file under
`docs/exec-plans/`; that tree remains historical only.

### Decision-to-artifact handoff index

- **Define Release Qualification Levels and Allowed Claims** is primarily
  transferred to the product specification; the design implements its
  cumulative fail-closed state mechanics.
- **Define Canonical Domain Capability Identity** and **Design the Domain Pack
  Interface and Seam** supply ADR 0002 and the deep design. The product spec
  retains only externally observable identity and isolation requirements.
- **Define Domain Pack Versioning and Compatibility** belongs primarily in the
  deep design, with compatibility outcomes retained as product acceptance.
- **Define Publishability Evidence and Decision Authority** supplies product
  requirements and ADR 0003; the deep design describes evidence validation
  without repeating the authority rationale.
- **Define Training Recommended Evidence** and **Specify the Workspace Training
  Recommendation Protocol** belong in product requirements and testing
  decisions, while schemas, deterministic statistics, and fail-closed import
  behavior belong in the deep design.
- **Align Workspace Release-Candidate Semantics**, **Define Contacts and Mobile
  Compatibility Fixtures**, and **Define the Workspace Tracer Proof** supply the
  product's acceptance boundary and the design's domain projections, migration
  fixtures, proof graph, and failure matrix.
- This decision owns the handoff convention itself. Later documents link here
  as decision provenance but do not reproduce this resolution comment.

### Handoff order

1. Write the product spec, deep design, and two ADRs as one coherent
   specification change; update `docs/README.md`, `ARCHITECTURE.md`, and the ADR
   index with concise links.
2. Review the product spec as the canonical acceptance contract and run the
   documentation validator.
3. Only after that contract is accepted, create the feature tracker and ordered
   implementation tickets. Every ticket links the product spec and, when
   relevant, the design or an ADR.
4. Hand implementation agents ticket files, not the Wayfinder comments or a
   parallel execution plan.

The Wayfinder map and resolution comments remain historical decision provenance
and a navigation index. Once the long-lived artifacts exist, they become the
authoritative specification, design, decision, language, and work-state sources
according to the ownership table above.
