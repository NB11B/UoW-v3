"""R4 reconstruction of archived U14-B goal-driven graph synthesis.

Source lineage:
NB11B/weights-on-the-fly@e9a143568180e612809dabd1352b023079c5001c
archive/orchestrator/orchestrator/graph_synthesis.py

This research-only port preserves the original capability while adapting the
certified output to the current canonical ResourceBoundTask/orchestration model.
It is not imported by src/uow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, Mapping, Optional, Set, Tuple

from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route
from uow.ontology import ALL_MATRIX_CELLS, MatrixCell, WorkCategory
from uow.orchestration.state import create_initial_orchestration_state
from uow.resources.requirement import ResourceBoundTask, ResourceRequirement, make_resource_domain_task
from uow.resources.state import ResourceState, set_authoritative_resource_state
from uow.state import WorldState, canonical_json


@dataclass(frozen=True)
class CandidateUoWSpec:
    identity: str
    source_category: str
    target_category: str
    mutations: Tuple[Mapping[str, Any], ...]
    resources: Mapping[str, Any] = field(default_factory=dict)
    dependencies: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateGraphProposal:
    goal: str
    model_id: str
    specs: Tuple[CandidateUoWSpec, ...]
    proposal_hash: str = ""

    def __post_init__(self) -> None:
        if not self.proposal_hash:
            payload = {
                "goal": self.goal,
                "model_id": self.model_id,
                "specs": [
                    {
                        "identity": s.identity,
                        "source": s.source_category,
                        "target": s.target_category,
                        "mutations": [dict(m) for m in s.mutations],
                        "resources": dict(s.resources),
                        "dependencies": list(s.dependencies),
                    }
                    for s in self.specs
                ],
            }
            object.__setattr__(
                self,
                "proposal_hash",
                hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
            )


class GoalDecompositionProposer:
    """Archived U14-B reference proposer seam, restored as research-only capability."""

    def __init__(self, model_id: str = "GoalDecompositionTransformer-v1") -> None:
        self._model_id = model_id

    def propose_graph(
        self,
        goal: str,
        *,
        inject_cycle: bool = False,
        inject_invalid_cell: bool = False,
    ) -> CandidateGraphProposal:
        if "reconcile" not in goal.lower():
            raise NotImplementedError(f"Goal pattern not supported: {goal!r}")

        src_cat = "InvalidCategory" if inject_invalid_cell else "Data"
        specs = [
            CandidateUoWSpec(
                "u1_load_source",
                src_cat,
                "Processes",
                ({"target": "loaded", "op": "SET", "operand": 1},),
                {"cpu_cores": 2, "ram_units": 4},
                (),
            ),
            CandidateUoWSpec(
                "u2_validate_schema",
                "Rules",
                "Data",
                ({"target": "validated", "op": "SET", "operand": 1},),
                {"cpu_cores": 1, "ram_units": 2},
                ("u1_load_source",),
            ),
            CandidateUoWSpec(
                "u3_reconcile",
                "Processes",
                "Data",
                ({"target": "reconciled", "op": "SET", "operand": 1},),
                {"cpu_cores": 4, "ram_units": 8},
                ("u2_validate_schema",),
            ),
            CandidateUoWSpec(
                "u4_audit_diffs",
                "Policies",
                "Rules",
                ({"target": "audited", "op": "SET", "operand": 1},),
                {"cpu_cores": 2, "ram_units": 4},
                ("u3_reconcile",),
            ),
            CandidateUoWSpec(
                "u5_publish_report",
                "People",
                "Guidance",
                ({"target": "published", "op": "SET", "operand": 1},),
                {"cpu_cores": 1, "ram_units": 2},
                ("u1_load_source",) if inject_cycle else ("u4_audit_diffs",),
            ),
        ]
        if inject_cycle:
            specs[0] = CandidateUoWSpec(
                "u1_load_source",
                src_cat,
                "Processes",
                ({"target": "loaded", "op": "SET", "operand": 1},),
                {"cpu_cores": 2, "ram_units": 4},
                ("u5_publish_report",),
            )
        return CandidateGraphProposal(goal, self._model_id, tuple(specs))


class DeterministicGraphCertifier:
    """Certifies candidate task decomposition before it can become executable work."""

    @classmethod
    def certify_and_build(
        cls,
        proposal: CandidateGraphProposal,
        host_resources: Optional[ResourceState] = None,
    ) -> tuple[
        bool,
        Optional[Dict[str, ResourceBoundTask]],
        Optional[WorldState],
        Optional[str],
    ]:
        identities: Set[str] = {s.identity for s in proposal.specs}
        if len(identities) != len(proposal.specs):
            return False, None, None, "DUPLICATE_UOW_IDENTITY"

        cat_map = {c.value: c for c in WorkCategory}
        for spec in proposal.specs:
            if spec.source_category not in cat_map or spec.target_category not in cat_map:
                return False, None, None, "INVALID_CATEGORY"
            cell = MatrixCell(cat_map[spec.source_category], cat_map[spec.target_category])
            if cell not in ALL_MATRIX_CELLS:
                return False, None, None, "INVALID_PAIRING"

        deps: Dict[str, Tuple[str, ...]] = {}
        for spec in proposal.specs:
            for dep in spec.dependencies:
                if dep not in identities:
                    return False, None, None, f"DANGLING_DEPENDENCY:{spec.identity}:{dep}"
            deps[spec.identity] = tuple(spec.dependencies)

        visiting: Set[str] = set()
        visited: Set[str] = set()

        def has_cycle(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dep in deps.get(node, ()):
                if has_cycle(dep):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        if any(has_cycle(node) for node in identities):
            return False, None, None, "CYCLIC_DEPENDENCY"

        registry: Dict[str, ResourceBoundTask] = {}
        initial_vars: Dict[str, Any] = {}

        for spec in proposal.specs:
            cell = MatrixCell(cat_map[spec.source_category], cat_map[spec.target_category])
            mutations = []
            for raw in spec.mutations:
                target = str(raw["target"])
                initial_vars[target] = 0
                mutations.append(
                    Mutation(
                        MutationOp[str(raw["op"])],
                        target,
                        raw.get("operand"),
                    )
                )

            req = ResourceRequirement(
                cpu_cores=int(spec.resources.get("cpu_cores", 1)),
                ram_units=int(spec.resources.get("ram_units", 1)),
                gpu_slots=int(spec.resources.get("gpu_slots", 0)),
                npu_slots=int(spec.resources.get("npu_slots", 0)),
            )
            registry[spec.identity] = make_resource_domain_task(
                spec.identity,
                [Route(Guard(GuardOp.ALWAYS), tuple(mutations))],
                req,
                matrix_cell=cell,
            )

        base = create_initial_orchestration_state(
            [s.identity for s in proposal.specs],
            deps,
            attributes=initial_vars,
        )
        initial = set_authoritative_resource_state(
            base,
            host_resources or ResourceState(),
        )
        return True, registry, initial, None
