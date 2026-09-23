"""Canonical Intel AI Boost OpenVINO NPU Adaptive Proposer (Gate U15.5)."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
import numpy as np
import openvino as ov
import torch

from uow.contracts import UoW
from uow.orchestration.state import OrchestrationState
from uow.proposer.base import AdaptiveProposer
from uow.proposer.identity import ModelIdentity
from uow.proposer.observation import AdaptationObservation
from uow.proposer.types import ModelProposal
from uow.resources.requirement import ResourceBoundTask
from uow.state import WorldState
from uow.transactions.descriptor import infer_footprint

from .features import CandidateFeatureEncoder, FEATURE_DIM
from .lifecycle import ModelLifecycleState, NPUModelLifecycleManager, StagedModel
from .model import UoWSchedulingNet, export_and_hash_onnx
from .training import extract_training_samples, train_surrogate_model


class IntelNPUAdaptiveProposer:
    """Canonical OpenVINO NPU adaptive proposer implementing the AdaptiveProposer contract (Gate U15.5).

    The model has ZERO authority to commit or mutate world state.
    Evaluates candidate UoW readiness using hardware compiled inference.
    Binds raw compiled ONNX bytes to ModelIdentity cryptographic lineage.
    """

    def __init__(
        self,
        device: str = "NPU",
        model_dir: Optional[Path] = None,
        model_id: str = "Intel_AI_Boost_NPU_Scheduler",
        model_version: str = "1.0.0",
        fail_closed: bool = True,
        initial_net: Optional[UoWSchedulingNet] = None,
        generation: int = 0,
        parent_model_hash: Optional[str] = None,
    ) -> None:
        self.device = device.upper()
        self.fail_closed = fail_closed
        self.model_dir = Path(model_dir or "artifacts/openvino_npu")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.encoder = CandidateFeatureEncoder()

        # Initialize OpenVINO Core
        self.core = ov.Core()
        available_devices = self.core.available_devices

        if self.device == "NPU":
            if "NPU" not in available_devices:
                if self.fail_closed:
                    raise RuntimeError(
                        "Physical OpenVINO NPU device is unavailable on host; "
                        "fallback to CPU is strictly forbidden for physical qualification."
                    )
                else:
                    self.device = "CPU"

        try:
            self.device_full_name = self.core.get_property(self.device, "FULL_DEVICE_NAME")
        except Exception:
            self.device_full_name = self.device

        # Internal PyTorch network (used for training updates)
        self.net = initial_net or UoWSchedulingNet()

        # Initialize lifecycle manager
        self.lifecycle = NPUModelLifecycleManager(
            model_dir=self.model_dir,
            core=self.core,
            device=self.device,
            model_id=model_id,
            model_version=model_version,
            fail_closed=fail_closed,
        )

        # Stage and promote initial model generation
        self.lifecycle.stage_generation(
            net=self.net,
            generation=generation,
            parent_identity=None,
        )
        self.lifecycle.promote_staged()

        # Feedback and audit buffers
        self.observations: List[AdaptationObservation] = []
        self.seen_observation_hashes: Set[str] = set()

        # Fault injection flags for falsification testing (Gate U15.5 negative controls)
        self.inject_crash_on_propose: bool = False
        self.inject_corrupt_schedule: bool = False

    @property
    def _identity(self) -> ModelIdentity:
        stage = self.lifecycle.active_stage
        if stage is None:
            raise RuntimeError("No active model stage in lifecycle manager")
        return stage.identity

    @property
    def _compiled_model(self) -> Any:
        stage = self.lifecycle.active_stage
        if stage is None:
            raise RuntimeError("No active model stage in lifecycle manager")
        return stage.compiled_model

    @property
    def _generation(self) -> int:
        stage = self.lifecycle.active_stage
        return stage.generation if stage else 0

    @property
    def _artifact_hash(self) -> str:
        return self._identity.model_artifact_hash

    def model_id(self) -> str:
        return self._identity.model_id

    def model_version(self) -> str:
        return self._identity.model_version

    def model_identity(self) -> ModelIdentity:
        return self._identity

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        """Evaluates ready candidates using compiled NPU inference and emits pure proposal."""
        if self.inject_crash_on_propose:
            raise RuntimeError("Injected NPU accelerator crash during propose()")

        # Pin active stage reference to guarantee atomic inference throughout propose()
        stage = self.lifecycle.active_stage
        if stage is None:
            raise RuntimeError("No active model stage in lifecycle manager")
        identity = stage.identity
        compiled = stage.compiled_model

        if not ready_candidates:
            return ModelProposal(
                model_id=identity.model_id,
                model_version=identity.model_version,
                input_state_hash=state.state_hash,
                input_sequence=state.sequence,
                input_epoch=state.sequence,
                candidate_schedule=(),
                predicted_metrics={"npu_latency_us": 0.0, "candidates_scored": 0.0, "batch_size": 0.0},
                model_artifact_hash=identity.model_artifact_hash,
                training_generation=identity.training_generation,
                parent_model_hash=identity.parent_model_hash,
                metadata={"device": self.device, "device_name": self.device_full_name},
            )

        # 1. Encode candidate feature vectors
        features_list = [
            self.encoder.encode(cid, graph, state, ready_candidates)
            for cid in ready_candidates
        ]
        # 2. Hardware NPU Inference (evaluated candidate-by-candidate to match static NPU shape (1, 14))
        t0 = time.perf_counter()
        output_tensor = compiled.output(0)
        scores: List[float] = []
        for feat in features_list:
            inp = feat[np.newaxis, :].astype(np.float32)
            s = float(compiled([inp])[output_tensor][0, 0])
            scores.append(s)
        latency_us = (time.perf_counter() - t0) * 1e6

        # 3. Rank candidates by neural score
        scored_candidates = sorted(
            zip(ready_candidates, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        if self.inject_corrupt_schedule:
            # Propose illegal tasks to test containment
            return ModelProposal(
                model_id=identity.model_id,
                model_version=identity.model_version,
                input_state_hash=state.state_hash,
                input_sequence=state.sequence,
                input_epoch=state.sequence,
                candidate_schedule=("illegal_unregistered_task_999",),
                model_artifact_hash=identity.model_artifact_hash,
                training_generation=identity.training_generation,
                parent_model_hash=identity.parent_model_hash,
                metadata={"device": self.device},
            )

        # 4. Construct candidate schedule avoiding intra-batch OCC hazards
        batch: List[str] = []
        batch_writes: Set[str] = set()

        for cid, _score in scored_candidates:
            item = graph.get(cid)
            if item is None:
                continue

            uow = item.uow if isinstance(item, ResourceBoundTask) else getattr(item, "uow", item)
            w_targets = set()
            if hasattr(uow, "Gamma"):
                _, route = uow.Gamma.select_route(state)
                _, w_targets = infer_footprint(route)

            if batch_writes.intersection(w_targets):
                continue  # Avoid OCC write-write hazard

            batch.append(cid)
            batch_writes.update(w_targets)

            # Cap batch size to max 4 concurrent tasks
            if len(batch) >= 4:
                break

        if not batch and ready_candidates:
            batch = [ready_candidates[0]]

        return ModelProposal(
            model_id=identity.model_id,
            model_version=identity.model_version,
            input_state_hash=state.state_hash,
            input_sequence=state.sequence,
            input_epoch=state.sequence,
            candidate_schedule=tuple(batch),
            predicted_metrics={
                "npu_latency_us": float(latency_us),
                "candidates_scored": float(len(ready_candidates)),
                "batch_size": float(len(batch)),
            },
            metadata={
                "device": self.device,
                "device_name": self.device_full_name,
                "model_artifact_hash": identity.model_artifact_hash,
            },
            model_artifact_hash=identity.model_artifact_hash,
            training_generation=identity.training_generation,
            parent_model_hash=identity.parent_model_hash,
        )

    def observe_feedback(self, observation: AdaptationObservation) -> None:
        """Buffers certified observations from the deterministic Judge."""
        if observation.observation_hash in self.seen_observation_hashes:
            return
        self.seen_observation_hashes.add(observation.observation_hash)
        self.observations.append(observation)

    def stage_update(
        self,
        graph: Optional[Mapping[str, Any]] = None,
        inject_compilation_failure: bool = False,
        inject_health_check_failure: bool = False,
    ) -> StagedModel:
        """Trains candidate weights on certified feedback and compiles into STAGING without altering active model."""
        if graph and self.observations:
            X, y = extract_training_samples(self.observations, self.encoder, graph)
            if len(X) > 0:
                train_surrogate_model(self.net, X, y, epochs=50)

        next_gen = self._generation + 1
        return self.lifecycle.stage_generation(
            net=self.net,
            generation=next_gen,
            parent_identity=self.model_identity(),
            inject_compilation_failure=inject_compilation_failure,
            inject_health_check_failure=inject_health_check_failure,
        )

    def promote_staged(self) -> ModelIdentity:
        """Atomically promotes the currently staged generation to ACTIVE."""
        self.observations.clear()
        return self.lifecycle.promote_staged()

    def rollback(self, generation: int) -> ModelIdentity:
        """Rolls back the active model to a previously compiled generation."""
        self.observations.clear()
        return self.lifecycle.rollback_to_generation(generation)

    def update(self, graph: Optional[Mapping[str, Any]] = None) -> ModelIdentity:
        """Atomically stages and promotes the next generation."""
        self.stage_update(graph=graph)
        return self.promote_staged()

    def branch_update(
        self,
        base_generation: int,
        graph: Optional[Mapping[str, Any]] = None,
    ) -> StagedModel:
        """Trains candidate weights and stages a new branch child directly from base_generation."""
        if graph and self.observations:
            X, y = extract_training_samples(self.observations, self.encoder, graph)
            if len(X) > 0:
                train_surrogate_model(self.net, X, y, epochs=50)

        return self.lifecycle.branch_generation(
            net=self.net,
            base_generation=base_generation,
        )

    def get_policy_graph(self) -> List[Dict[str, Any]]:
        """Returns the policy memory DAG from the lifecycle manager."""
        return self.lifecycle.get_policy_graph()
