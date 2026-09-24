"""Stochastic and adversarial proposer for aggressively falsifying the trust boundary (Gate U14)."""
from __future__ import annotations

import random
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ...state import WorldState
from ...proposer.base import BaseProposer
from ...proposer.types import ModelProposal


class RandomProposer(BaseProposer):
    """Deliberately stochastic and adversarial proposer for falsifying the proposal boundary.

    Can inject:
    - Non-existent or unready task IDs (illegal dependencies - Gate U14.3)
    - Conflicting tasks targeting shared variables (OCC conflicts - Gate U14.4)
    - Tasks demanding excessive resources (resource over-allocation - Gate U14.5)
    - Obsolete input state hashes and sequences (stale state - Gate U14.6)
    - Exceptions to test fallback activation (proposer failure - Gate U14.7)
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        *,
        inject_illegal_deps: bool = False,
        inject_occ_conflict: bool = False,
        inject_overallocation: bool = False,
        inject_stale_epoch: bool = False,
        inject_crash: bool = False,
    ) -> None:
        self.rng = random.Random(seed) if seed is not None else random.Random()
        self.inject_illegal_deps = inject_illegal_deps
        self.inject_occ_conflict = inject_occ_conflict
        self.inject_overallocation = inject_overallocation
        self.inject_stale_epoch = inject_stale_epoch
        self.inject_crash = inject_crash

    def model_id(self) -> str:
        return "RandomProposer"

    def model_version(self) -> str:
        return "0.1.0-stochastic"

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        if self.inject_crash:
            raise RuntimeError("Injected model crash/timeout in RandomProposer")

        state_hash = (
            "stale_hash_0000000000000000000000000000000000000000000000000000000000000000"
            if self.inject_stale_epoch
            else state.state_hash
        )
        seq = state.sequence - 5 if self.inject_stale_epoch else state.sequence

        candidates: List[str] = list(ready_candidates)

        # 1. Injected illegal dependency (task not ready or not in graph)
        if self.inject_illegal_deps:
            candidates.insert(0, "phantom_task_unready")

        # 2. Injected OCC conflict (duplicate identical task in same batch)
        if self.inject_occ_conflict and len(candidates) >= 1:
            candidates = [candidates[0], candidates[0]]

        # 3. Injected resource over-allocation (request all tasks concurrently)
        if self.inject_overallocation:
            chosen: Tuple[str, ...] = tuple(candidates)
        else:
            if candidates:
                sample_size = self.rng.randint(1, len(candidates))
                shuffled = list(candidates)
                self.rng.shuffle(shuffled)
                chosen = tuple(shuffled[:sample_size])
            else:
                chosen = ()

        return ModelProposal(
            model_id=self.model_id(),
            model_version=self.model_version(),
            input_state_hash=state_hash,
            input_sequence=seq,
            input_epoch=seq,
            candidate_schedule=chosen,
            predicted_metrics={"confidence": 0.5, "random_entropy": self.rng.random()},
        )
