# R7 Additive Repository Migration

The research branch now exposes the target architectural layers at repository root while retaining all current production paths.

Current state:

```text
legacy/canonical implementation: src/uow, integrations, qualification, foundations
validated research model:       architecture/
target structural surfaces:     specification, implementations, realizations, experiments, conformance
```

Rules:
1. No live file is moved in R7.1.
2. No current import path changes.
3. No experiment or evidence artifact is deleted.
4. A target layer only becomes canonical after the full reconstruction/conformance suite passes through its facade.
5. Physical qualification is never inferred from portable parity.

See `architecture/r7_current_target_map.yaml` for file-level disposition.