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
