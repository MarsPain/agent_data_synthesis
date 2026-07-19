# ISSUE-0002: Semantic Duplicate Detection

- **Status:** Deferred
- **Assignee:** Unassigned
- **Parent spec:** [Semantic Duplicate Detection](../docs/product-specs/semantic-duplicate-detection.md)
- **Dependencies:** Provider and representation choice require cost/benefit
  evidence at representative dataset volume.
- **Legacy record:** [TD-0002](../docs/exec-plans/tech-debt/README.md#td-0002-semantic-duplicate-detection-is-not-yet-implemented)

## Activation Trigger

Start implementation when dataset volume exceeds reliable manual review or
evaluation shows that paraphrased or action-equivalent tasks materially inflate
coverage or curriculum metrics.

## Current Disposition

Retain exact instruction-plus-tool-sequence duplicate admission. Do not add an
embedding or local-model dependency before representative evidence establishes
the quality benefit and operating cost.
