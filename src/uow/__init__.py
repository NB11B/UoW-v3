"""Unit-of-Work (UoW) Protocol and Runtime Architecture.

Minimal Root API:
    from uow import UoW, WorldState, execute

Namespaced Subsystems:
    uow.authority  - PROPOSE -> CERTIFY -> COMMIT, distributed quorum, evidence ledgers
    uow.runtime    - DAG orchestration, OCC transactions, resource leases, effects, proposers
    uow.autonomy   - Goal profiles, gap/deficit analysis, autonomous repair, closure
    uow.semantic   - Semantic mediation, ontology matrix, governed egress filters
    uow.economics  - Economic observations (compute/energy/market costs) as protocol data
    uow.protocol   - Canonical schemas and wire envelope definitions
    uow.adapters   - Hardware and neural model adapters (e.g. OpenVINO NPU)

Backward compatibility:
    from uow.compat.v2 import ...
"""
from __future__ import annotations

# Canonical Minimal Root API
from .contracts import UoW
from .state import WorldState
from .engine import execute

# Namespaces
from . import authority as authority
from . import runtime as runtime
from . import autonomy as autonomy
from . import semantic as semantic
from . import economics as economics
from . import protocol as protocol
from . import adapters as adapters

__all__ = [
    "UoW",
    "WorldState",
    "execute",
    "authority",
    "runtime",
    "autonomy",
    "semantic",
    "economics",
    "protocol",
    "adapters",
]
