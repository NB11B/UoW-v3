# Semantic Facade — R7.2

Status: additive research surface.

The Python facade under `implementations/python/uow_architecture_facade` exposes the three seams validated in R6 without moving or replacing `src/uow`:

1. Application:
   `Proposal -> Conformance -> Authorization -> AuthorizedTransition -> Evidence`
2. Authority provider:
   `collect_votes -> form_authorization -> apply_authorization`
3. Typed conformance:
   one invocation interface with domain-specific validators preserved.

The facade is intentionally thin. It does not duplicate implementation logic.

During R7:
- canonical `src/uow` remains the production/reference Python implementation;
- `architecture/shadow/python/uow_shadow` remains the validated reconstruction layer;
- `implementations/python/uow_architecture_facade` is the proposed target-layout access surface.

R7.2 acceptance requires dual-layout semantic parity before any production import is redirected.

The facade must also remain compatible with the frozen reference oracles:
- A2 portable capstone;
- A3 adaptive compute efficiency;
- Policy Orchestrator P1-P5;
- A4 ontology adaptation as an unqualified forward-compatibility constraint.
