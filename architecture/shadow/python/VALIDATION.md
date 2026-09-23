# R3.0 Validation Note

The initial shadow Python package was syntax-checked before commit.

The tests under architecture/shadow/python/tests have been created but have not yet been executed against the repository runtime in this branch.

No qualification claim should be inferred from their existence.

Initial intended parity checks:
- core deterministic certification accept/reject;
- resource capacity decision;
- OCC stale-read rejection;
- external receipt binding;
- typed set-inclusion matching;
- authority lattice matching;
- distinct-voter quorum semantics;
- freshness semantics.

The next action is to execute these tests in a repository environment and treat any mismatch as a research finding.
