"""Portable closed-loop adaptive proposer with online parameter learning (Gates U15.3, U15.4)."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..contracts import UoW
from ..resources.requirement import ResourceBoundTask, ResourceRequirement
from ..state import WorldState, canonical_json
from ..transactions.descriptor import infer_footprint
from .identity import ModelIdentity
from .observation import AdaptationObservation
from .types import ModelProposal


class PortableAdaptiveProposer:
    """Portable closed-loop adaptive proposer implementing continual parameter adaptation.

    Learns optimal task batching and resource assignment from deterministic Judge feedback.
    The model has ZERO authority to commit or mutate world state.
    All supervision is certified by deterministic authority.

    Under workload drift (e.g. CPU-heavy vs GPU-heavy availability), the proposer
    adapts its policy weights to minimize rejections and fallback activation.
    """

    def __init__(
        self,
        model_id: str = "PortableAdaptiveProposer",
        model_version: str = "1.0.0",
        initial_weights: Optional[Mapping[str, float]] = None,
        learning_rate: float = 0.2,
    ) -> None:
        self._model_id = model_id
        self._model_version = model_version
        self._learning_rate = learning_rate

        # Policy weights: scoring weights for task features
        # e.g., preference for CPU tasks, GPU tasks, NPU tasks, priority, batch size
        self.weights: Dict[str, float] = {
            "cpu_affinity": 1.0,
            "gpu_affinity": 1.0,
            "npu_affinity": 1.0,
            "cpu_capacity": 8.0,
            "gpu_capacity": 8.0,
            "npu_capacity": 8.0,
            "priority_weight": 0.5,
            "batch_capacity_target": 4.0,
        }
        if initial_weights:
            self.weights.update(initial_weights)

        self._generation = 0
        self._artifact_hash = self._compute_artifact_hash(self.weights)
        self._identity = ModelIdentity(
            model_id=self._model_id,
            model_version=self._model_version,
            model_artifact_hash=self._artifact_hash,
            training_generation=self._generation,
        )

        # Observation buffer and deduplication set
        self.observation_buffer: List[AdaptationObservation] = []
        self.seen_observation_hashes: Set[str] = set()
        self.dropped_stale_count: int = 0
        self.dropped_duplicate_count: int = 0
        self.dropped_corrupt_count: int = 0
        self.last_observed_sequence: int = -1

        # Checkpoint snapshot for atomic rollback
        self._last_valid_snapshot = copy.deepcopy(self.weights)
        self._last_valid_identity = self._identity

        # Fault injection flags for falsification (Gate U15.4)
        self.inject_crash_on_update: bool = False
        self.inject_corrupt_weights_on_update: bool = False
        self.accept_corrupted_feedback: bool = False

    @staticmethod
    def _compute_artifact_hash(weights: Mapping[str, float]) -> str:
        payload = {str(k): round(float(v), 6) for k, v in sorted(weights.items())}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def model_id(self) -> str:
        return self._identity.model_id

    def model_version(self) -> str:
        return self._identity.model_version

    def model_identity(self) -> ModelIdentity:
        return self._identity

    def score_candidate(self, task_id: str, task: Any) -> float:
        """Scores a candidate task using current learned policy weights."""
        req: Optional[ResourceRequirement] = None
        if isinstance(task, ResourceBoundTask):
            req = task.requirement
        elif hasattr(task, "requirement"):
            req = task.requirement
        elif hasattr(task, "resources") and isinstance(task.resources, ResourceRequirement):
            req = task.resources

        score = 0.0
        if req is not None:
            score += self.weights.get("priority_weight", 0.5) * float(req.priority)
            if req.cpu_cores > 0:
                score += self.weights.get("cpu_affinity", 1.0) * float(req.cpu_cores)
            if req.gpu_slots > 0:
                score += self.weights.get("gpu_affinity", 1.0) * float(req.gpu_slots)
            if req.npu_slots > 0:
                score += self.weights.get("npu_affinity", 1.0) * float(req.npu_slots)
        else:
            score = 1.0
        return score

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        """Emits candidate schedule proposal scored by learned policy weights.

        Zero authority: emitted proposal must be certified by the Judge.
        """
        if not ready_candidates:
            return ModelProposal(
                model_id=self.model_id(),
                model_version=self.model_version(),
                input_state_hash=state.state_hash,
                input_sequence=state.sequence,
                input_epoch=state.sequence,
                candidate_schedule=(),
                model_artifact_hash=self._identity.model_artifact_hash,
                training_generation=self._identity.training_generation,
                parent_model_hash=self._identity.parent_model_hash,
            )

        # Score and rank candidates by policy
        ranked = sorted(
            ready_candidates,
            key=lambda cid: self.score_candidate(cid, graph.get(cid)),
            reverse=True,
        )

        # Greedily construct batch up to estimated capacity target
        batch: List[str] = []
        batch_writes: Set[str] = set()
        accum_cpu = 0
        accum_gpu = 0
        accum_npu = 0

        for cid in ranked:
            item = graph.get(cid)
            if item is None:
                continue

            req: Optional[ResourceRequirement] = None
            if isinstance(item, ResourceBoundTask):
                req = item.requirement
            elif hasattr(item, "requirement"):
                req = item.requirement
            elif hasattr(item, "resources") and isinstance(item.resources, ResourceRequirement):
                req = item.resources

            req_cpu = req.cpu_cores if req else 0
            req_gpu = req.gpu_slots if req else 0
            req_npu = req.npu_slots if req else 0

            # Check if candidate exceeds learned capacity limit
            if accum_cpu + req_cpu > self.weights.get("cpu_capacity", 8.0):
                continue
            if accum_gpu + req_gpu > self.weights.get("gpu_capacity", 8.0):
                continue
            if accum_npu + req_npu > self.weights.get("npu_capacity", 8.0):
                continue

            # Footprint conflict check (OCC avoidance heuristic)
            uow = item.uow if isinstance(item, ResourceBoundTask) else getattr(item, "uow", item)
            w_targets = set()
            if hasattr(uow, "Gamma"):
                _, route = uow.Gamma.select_route(state)
                _, w_targets = infer_footprint(route)

            if batch_writes.intersection(w_targets):
                continue  # Skip conflicting task to avoid intra-batch OCC hazard

            batch.append(cid)
            batch_writes.update(w_targets)
            accum_cpu += req_cpu
            accum_gpu += req_gpu
            accum_npu += req_npu

            # Limit batch size to learned target
            target_size = max(1, int(round(self.weights.get("batch_capacity_target", 2.0))))
            if len(batch) >= target_size:
                break

        if not batch and ready_candidates:
            batch = [ready_candidates[0]]

        return ModelProposal(
            model_id=self.model_id(),
            model_version=self.model_version(),
            input_state_hash=state.state_hash,
            input_sequence=state.sequence,
            input_epoch=state.sequence,
            candidate_schedule=tuple(batch),
            predicted_metrics={
                "policy_generation": float(self._generation),
                "batch_size": float(len(batch)),
            },
            metadata={"learner": "PortableAdaptiveProposer"},
            model_artifact_hash=self._identity.model_artifact_hash,
            training_generation=self._identity.training_generation,
            parent_model_hash=self._identity.parent_model_hash,
        )

    def observe_feedback(self, observation: AdaptationObservation) -> None:
        """Buffers certified deterministic authority feedback for model adaptation."""
        # 1. Verification of cryptographic observation integrity
        expected_hash = AdaptationObservation.calculate_hash(
            observation_id=observation.observation_id,
            pre_state_hash=observation.pre_state_hash,
            pre_sequence=observation.pre_sequence,
            pre_epoch=observation.pre_epoch,
            proposal_hash=observation.proposal_hash,
            model_id=observation.model_id,
            model_version=observation.model_version,
            model_artifact_hash=observation.model_artifact_hash,
            training_generation=observation.training_generation,
            parent_model_hash=observation.parent_model_hash,
            accepted_tasks=observation.accepted_tasks,
            rejected_tasks=dict(observation.rejected_tasks),
            fallback_triggered=observation.fallback_triggered,
            committed=observation.committed,
            post_state_hash=observation.post_state_hash,
            post_sequence=observation.post_sequence,
            certificate_hash=observation.certificate_hash,
        )
        if observation.observation_hash != expected_hash:
            self.dropped_corrupt_count += 1
            if not self.accept_corrupted_feedback:
                return  # Drop tampered/forged feedback

        # 2. Duplicate observation detection
        if observation.observation_hash in self.seen_observation_hashes:
            self.dropped_duplicate_count += 1
            return
        self.seen_observation_hashes.add(observation.observation_hash)

        # 3. Stale sequence detection
        if observation.pre_sequence < self.last_observed_sequence:
            self.dropped_stale_count += 1
            return
        self.last_observed_sequence = observation.pre_sequence

        self.observation_buffer.append(observation)

    def update(self) -> ModelIdentity:
        """Performs atomic policy parameter update from buffered feedback.

        Transitions model generation: theta_t -> theta_{t+1}.
        Zero authority: does not mutate world state.
        """
        # Save snapshot for atomic rollback
        prev_weights = copy.deepcopy(self.weights)
        prev_identity = self._identity

        try:
            if self.inject_crash_on_update:
                raise RuntimeError("Simulated crash during model parameter update!")

            if self.inject_corrupt_weights_on_update:
                # Catastrophic poisoning: corrupt all weights to negative infinity
                for k in self.weights:
                    self.weights[k] = -1e9
            else:
                # Perform gradient/heuristic update based on authoritative feedback
                for obs in self.observation_buffer:
                    if obs.rejected_tasks:
                        # Negative feedback: penalize features associated with rejections
                        for task_id, reason in obs.rejected_tasks.items():
                            if "RESOURCE_CAPACITY_EXCEEDED" in reason:
                                # Rejection due to resource over-subscription: decrease batch target
                                self.weights["batch_capacity_target"] = max(
                                    1.0,
                                    self.weights["batch_capacity_target"] - self._learning_rate * 0.8,
                                )
                                # Penalize capacity and affinity if reason cites specific accelerator
                                if "gpu" in task_id.lower():
                                    self.weights["gpu_capacity"] = max(
                                        1.0,
                                        self.weights["gpu_capacity"] - self._learning_rate * 3.5,
                                    )
                                    self.weights["gpu_affinity"] = max(
                                        -5.0,
                                        self.weights["gpu_affinity"] - self._learning_rate * 2.0,
                                    )
                                if "cpu" in task_id.lower():
                                    self.weights["cpu_capacity"] = max(
                                        1.0,
                                        self.weights["cpu_capacity"] - self._learning_rate * 3.5,
                                    )
                                    self.weights["cpu_affinity"] = max(
                                        -5.0,
                                        self.weights["cpu_affinity"] - self._learning_rate * 2.0,
                                    )
                                if "npu" in task_id.lower():
                                    self.weights["npu_capacity"] = max(
                                        1.0,
                                        self.weights["npu_capacity"] - self._learning_rate * 3.5,
                                    )
                                    self.weights["npu_affinity"] = max(
                                        -5.0,
                                        self.weights["npu_affinity"] - self._learning_rate * 2.0,
                                    )
                            elif "OCC" in reason:
                                # Intra-batch OCC collision: favor smaller batches
                                self.weights["batch_capacity_target"] = max(
                                    1.0,
                                    self.weights["batch_capacity_target"] - self._learning_rate * 0.5,
                                )
                    elif obs.committed and obs.accepted_tasks:
                        # Positive feedback: clean batch without rejections reinforces current target
                        self.weights["batch_capacity_target"] = min(
                            8.0,
                            self.weights["batch_capacity_target"] + self._learning_rate * 0.1,
                        )

            self.observation_buffer.clear()
            self._generation += 1
            new_hash = self._compute_artifact_hash(self.weights)
            self._identity = self._identity.child_identity(new_hash)
            self._last_valid_snapshot = copy.deepcopy(self.weights)
            self._last_valid_identity = self._identity
            return self._identity

        except Exception as e:
            # Atomic rollback on crash or exception
            self.weights = copy.deepcopy(prev_weights)
            self._identity = prev_identity
            raise e
