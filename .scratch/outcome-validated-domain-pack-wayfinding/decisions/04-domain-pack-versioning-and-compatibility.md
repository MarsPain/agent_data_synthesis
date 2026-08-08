# Define Domain Pack Versioning and Compatibility

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Canonical Domain Capability Identity](02-canonical-domain-capability-identity.md), [Design the Domain Pack Interface and Seam](03-domain-pack-interface-seam.md)

## Question

Which Domain Pack changes require new identities or versions, how are legacy
task and capability names interpreted, and what compatibility guarantees keep
existing manifests, release packs, profiles, and evidence reports readable
during migration?

## Resolution comment

Use immutable composition versions, independently versioned semantic contracts,
and explicit compatibility assessments. Do not use one global alias table or
one undifferentiated `compatible` boolean.

### Identity and version rules

An exact Domain Pack reference contains:

```text
(domain_pack_id, pack_version, pack_hash)
```

- `domain_pack_id` changes only when the bounded semantic authority changes: a
  domain is split, merged, or replaced by a meaningfully different domain. A
  packaging move, provider change, runtime change, or display rename does not
  create a new Domain Pack identity.
- `pack_version` is an immutable human-readable composition version;
  `pack_hash` binds its canonical content. Reusing a version with different
  content is invalid. Version labels such as `workspace_tasks_pack_v1` are
  opaque monotonic identifiers, not promises that semantic-version arithmetic
  can determine compatibility.
- Any change that can alter `plan`, `open`, a `DomainRun` result, `assess`, or
  the meaning/admissibility of evidence requires a new Domain Pack version.
  This includes capability references, task projections, coverage catalogs or
  profiles, evaluation suites or thresholds, mutation policies, release
  completeness, default semantic policy, compatibility mappings, and required
  runtime contracts. Documentation and display-only metadata do not.
- A materially different claim receives a new `capability_key`. A change to the
  proof or acceptance contract for the same continuous claim receives a new
  capability contract version. Tightening a threshold therefore cannot silently
  reuse old evidence; a label-only rename changes neither identity nor version.
- Task types, coverage catalogs/profiles, evaluation suites, mutation policies,
  artifact schemas, and runtimes retain their own identities and versions. The
  Domain Pack version selects one closed, internally consistent set; it does not
  replace those versions.
- Runtime identity remains independent. A new runtime implementation may serve
  the same Domain Pack version only when it satisfies the already-declared
  runtime contract and conformance requirements; evidence still records its
  exact runtime version. Changing the required runtime behavior requires a new
  runtime contract and Domain Pack version.
- Persisted artifact schema versions change when serialized shape or validation
  semantics change. A schema version says how to read a record; a Domain Pack
  version says which domain semantics produced or assessed it.

Bug fixes are classified by observable effect. A verifier or generator fix that
can change acceptance, evidence, or deterministic output requires a new
component version and Domain Pack version even if the intended capability
meaning is unchanged. A refactor proven behavior-preserving does not.

### Compatibility is multi-dimensional

Every compatibility decision reports separate statuses for:

1. **Readability:** a declared reader can parse and validate the historical
   schema under its original rules.
2. **Runnability:** a versioned adapter can compile the input into a valid
   current Domain plan without guessing.
3. **Semantic equivalence:** the mapping is lossless for the relevant domain
   meaning rather than merely similar in spelling.
4. **Evidence admissibility:** the source contains enough exact evidence to
   contribute to the requested current claim.

An artifact may therefore be readable and historically verifiable while being
non-runnable or ineligible for current qualification. Unknown or ambiguous
status on any required axis fails closed.

### Legacy interpretation

- A compatibility mapping is keyed by source artifact schema/version, field or
  projection kind, legacy value, and target reference. The mapping and its hash
  are versioned and selected by the Domain Pack. Never normalize equal strings
  globally across task, capability, coverage, evaluation, tool, and runtime
  namespaces.
- Aliases are accepted only at ingestion. Canonical writers emit exact Domain
  Pack, capability, component, and runtime references; they never emit a legacy
  alias or infer a capability from a task/tool label.
- A migrated record preserves the original bytes or content hash, original
  reference, mapping version/hash, target reference, and derivation lineage.
  Migration creates a new artifact and hash; it never rewrites a manifest,
  release pack, report, or evidence record in place.
- Unknown, cross-pack, unsupported-version, many-target, or context-free legacy
  references are rejected. One legacy value may map differently in distinct
  projection kinds only when both mappings are explicit.

For the initial migration, `contacts` in the seed-domain field of a supported
legacy run profile maps to the logical Domain Pack `contacts`; a
`contacts_fixture` value in a runtime field remains the runtime id. Likewise,
legacy `mobile_messages_fixture` and `workspace_tasks_fixture` values may map to
logical packs only in fields whose contracts denote a semantic domain. Their
exact task/capability mappings are not inferred from suffix removal:
[Align Workspace Release-Candidate Semantics](07-workspace-release-candidate-semantics.md)
owns Workspace alignment, and
[Define Contacts and Mobile Compatibility Fixtures](08-contacts-mobile-compatibility-fixtures.md)
owns the checked-in compatibility matrix for the other two domains.

### Migration guarantees

- The first Domain Pack reader set must preserve the currently checked-in
  legacy floor: run profiles `v1` through `v4`, manifests `v1` and `v2`, release
  packs `v1` and `v2`, and the historical evaluation/report forms already
  accepted by repository contract tests. Support is explicit, not open-ended;
  removing a reader or adapter is a breaking support-policy change and requires
  a declared migration path.
- Supported legacy run profiles remain runnable through scoped adapters when
  every required input maps losslessly. The resulting plan and new artifacts
  use canonical references while retaining the original profile hash and
  migration lineage.
- Historical manifests, reports, evidence, and release packs remain readable
  and verifiable against their original schemas and claim semantics. Their
  historical qualification is not silently renamed to a current
  qualification.
- Missing Domain Pack versions, capability references, or proof facts cannot be
  manufactured from task names, tool traces, coverage labels, or an alias map.
  Such evidence is `historical_only` / `insufficient_evidence` for current
  Release Candidate, Publishable, and Training Recommended claims.
- A lossless migration may make evidence current-claim eligible only when every
  required fact was already explicit and equivalent in the source. Otherwise
  the data must be re-executed or re-evaluated under the target Domain Pack.

The human accepted this readability-without-automatic-promotion boundary on
2026-08-07. It preserves old workflows and historical verification without
allowing compatibility code to mint stronger evidence retroactively.
