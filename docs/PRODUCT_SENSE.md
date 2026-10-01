# Product Sense

The framework serves engineers building inspectable Agent training datasets.
It emits executable trajectories with task, tool, observation, assessment, and
lineage evidence. The useful unit is an Episode that can be replayed and
reviewed, not a flat instruction-response pair.

The current supported path is local, single-process synthesis across Contacts,
Mobile Messages, and Workspace Tasks. Bounded remote model calls are optional
and explicitly authorized. Dataset publication, downstream model improvement,
and human approval require separate evidence; they are not inferred from a
successful deterministic run.
