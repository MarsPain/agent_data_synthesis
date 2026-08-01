# Representative Structural Taxonomy

## Purpose

`representative_structural_taxonomy_v1` provides one like-for-like classifier
for legacy representative samples and coverage-driven campaign samples. It
measures executed task structure without relying on natural-language wording or
on coverage metadata that legacy samples do not contain.

The implementation lives in
[`synthesis/structural_taxonomy.py`](../../synthesis/structural_taxonomy.py).
Its canonical definition is hash-bound in every comparison report.

## Family Features

A classified family is the deterministic combination of:

- domain and task type;
- ordered required-tool sequence;
- primary selector argument fields;
- read-only or state-changing execution;
- values bound from an earlier tool observation into a later action; and
- the structural change from a failed branch selector to its accepted fallback.

Cross-step bindings are represented as field paths such as
`search_phone_messages.thread_id->draft_message_reply.thread_id`. Recovery
signatures record added, removed, or changed selector fields and categorical
value changes such as token expansion, token-order restoration, punctuation
normalization, or replacement of an email-shaped selector.

Instruction text, provider identity, coverage assignment identity, and coverage
cell identity are excluded. A coverage-driven sample therefore receives the
same family as a legacy sample with the same executed structure.

## Catalog Authoring Implications

Catalog authors should expand the reachable executable state-action graph, not
manufacture additional labels for an unchanged graph. Ordered tool topology,
read-only versus state-changing behavior, observation-to-action bindings, and
recovery transitions are the strongest reusable sources of structural
variation because they change what an agent must execute and what a verifier
can observe.

A meaningful state-changing sequence is especially high leverage: one task may
combine a new tool sequence, a durable state transition, values bound from
earlier observations, and independent final-state verification. It is neither
required nor sufficient for a new family. The mutation must be requested and
admitted, its arguments must have valid provenance, and the resulting state
must be independently verified. Adding a redundant mutation or padding a
trajectory with unnecessary tools is not valid structural diversity.

Likewise, additional coverage cells do not prove additional families. New
groundings, selector values, instructions, or cell identities may legitimately
increase sample variety while remaining in an existing structural family.
Cross-scale evidence must therefore classify executed samples under the same
taxonomy and fail closed when the distinct-family count does not grow. The
[target-30 provider campaign](../generated/representative-coverage-campaign-validation.md)
demonstrates this distinction: contacts fulfilled an additional locally named
cell without adding a common structural family.

## Fail-Closed Classification

A sample is unclassifiable when the classifier cannot obtain valid task
constraints, a trajectory action, primary arguments, or coherent branch
lineage. Reports retain total classified and unclassifiable counts plus bounded
reason counts. Unclassifiable samples are not silently assigned to an
`unknown` family and are excluded from the largest-family denominator.

## Comparison Contract

`structural_taxonomy_comparison_v1` records the taxonomy identity and hash,
family counts, distinct-family count, largest-family count and share, and
unclassifiable counts for both inputs. Deltas are computed from those two
summaries under the same taxonomy version.

The comparison is structural evidence only. It does not replace execution,
verification, safety, provenance, representative, release, or downstream
evaluation gates.
