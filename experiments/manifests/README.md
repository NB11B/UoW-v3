# Experiment Manifest Surface

R7 exposes experiment reconstruction through this top-level surface without moving canonical manifests yet.

The index points to:
- all current portable reconstruction manifests under `architecture/experiments`;
- the frozen A3 and P1–P5 reference-oracle manifest;
- A4 as a conceptual/unqualified ontology frontier.

This is intentionally an index, not a copy. Evidence and historical provenance remain at their qualified locations.

R7 cutover must preserve the invariant:

[
\forall e \in \mathcal{E}_{qualified},
\quad Reconstruct(TargetLayout,e)=PASS
]

The target layout may reorganize implementations, but experiment identity and evidence scope must remain stable.
