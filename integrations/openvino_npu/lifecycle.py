"""
Model lifecycle management for OpenVINO Intel AI Boost NPU Proposers (Gate U15.6).

Provides:
1. Lifecycle state machine: STAGING, ACTIVE, DRAINING, RETIRED, FAILED.
2. Staged compilation: Compiles theta_{t+1} in staging without touching active inference.
3. Health check verification: Validates output sanity (finite, expected shapes) before activation.
4. Atomic pointer swap: Thread-safe, non-blocking swap of active model pointer.
5. Rollback on failure: Staged failure leaves active model completely undisturbed.
6. Restart recovery: Recovers latest certified generation from durable disk manifest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import openvino as ov

from uow import ModelIdentity
from .features import CandidateFeatureEncoder, FEATURE_DIM
from .model import UoWSchedulingNet, export_and_hash_onnx


class ModelLifecycleState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    STAGING = "STAGING"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


@dataclass
class StagedModel:
    generation: int
    identity: ModelIdentity
    onnx_path: Path
    compiled_model: Any
    state: ModelLifecycleState = ModelLifecycleState.STAGING
    health_checked: bool = False
    compile_latency_ms: float = 0.0
    created_at: float = field(default_factory=time.time)


class NPUModelLifecycleManager:
    """Manages compiled model stages, health verification, atomic promotion, and restart recovery."""

    MANIFEST_FILENAME = "model_lineage_manifest.json"

    def __init__(
        self,
        model_dir: Path,
        core: ov.Core,
        device: str = "NPU",
        model_id: str = "Intel_AI_Boost_NPU_Scheduler",
        model_version: str = "1.0.0",
        fail_closed: bool = True,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.core = core
        self.device = device.upper()
        self.model_id = model_id
        self.model_version = model_version
        self.fail_closed = fail_closed
        self._lock = threading.Lock()

        self._active_stage: Optional[StagedModel] = None
        self._staging_stage: Optional[StagedModel] = None
        self._stages_by_gen: Dict[int, StagedModel] = {}
        self._stages_by_hash: Dict[str, StagedModel] = {}

    @property
    def active_stage(self) -> Optional[StagedModel]:
        with self._lock:
            return self._active_stage

    @property
    def staging_stage(self) -> Optional[StagedModel]:
        with self._lock:
            return self._staging_stage

    def stage_generation(
        self,
        net: UoWSchedulingNet,
        generation: int,
        parent_identity: Optional[ModelIdentity] = None,
        inject_compilation_failure: bool = False,
        inject_health_check_failure: bool = False,
    ) -> StagedModel:
        """Compiles a candidate generation in staging, performs health check, and holds for activation."""
        if inject_compilation_failure:
            raise RuntimeError("Injected accelerator compilation failure during staging")

        gen_dir = self.model_dir / f"gen_{generation}"
        gen_dir.mkdir(parents=True, exist_ok=True)
        onnx_file = gen_dir / "model.onnx"

        # 1. Export ONNX and compute cryptographic SHA-256 byte digest
        _, artifact_hash = export_and_hash_onnx(net, onnx_file)

        # 2. Compile onto target device
        t0 = time.perf_counter()
        ov_model = self.core.read_model(str(onnx_file))
        compiled = self.core.compile_model(ov_model, self.device)
        compile_ms = (time.perf_counter() - t0) * 1000.0

        # 3. Form ModelIdentity
        identity = (
            parent_identity.child_identity(new_artifact_hash=artifact_hash)
            if parent_identity is not None
            else ModelIdentity(
                model_id=self.model_id,
                model_version=self.model_version,
                model_artifact_hash=artifact_hash,
                training_generation=generation,
                metadata={"device": self.device},
            )
        )

        stage = StagedModel(
            generation=generation,
            identity=identity,
            onnx_path=onnx_file,
            compiled_model=compiled,
            state=ModelLifecycleState.STAGING,
            health_checked=False,
            compile_latency_ms=compile_ms,
        )

        # 4. Mandatory Pre-Activation Health Check
        if inject_health_check_failure:
            stage.state = ModelLifecycleState.FAILED
            raise ValueError("Injected health check failure: model output contains invalid non-finite values")

        self._run_health_check(stage)

        with self._lock:
            self._staging_stage = stage
            self._stages_by_gen[generation] = stage
            self._stages_by_hash[identity.model_artifact_hash] = stage

        return stage

    def _run_health_check(self, stage: StagedModel) -> None:
        """Executes a diagnostic inference probe to ensure model output sanity."""
        dummy_input = np.zeros((1, FEATURE_DIM), dtype=np.float32)
        out_tensor = stage.compiled_model.output(0)
        output = stage.compiled_model([dummy_input])[out_tensor]

        if output.shape != (1, 1):
            stage.state = ModelLifecycleState.FAILED
            raise ValueError(f"Health check failed: expected shape (1, 1), got {output.shape}")

        val = float(output[0, 0])
        if np.isnan(val) or np.isinf(val):
            stage.state = ModelLifecycleState.FAILED
            raise ValueError(f"Health check failed: output is non-finite: {val}")

        stage.health_checked = True

    def promote_staged(self) -> ModelIdentity:
        """Atomically promotes the currently staged model to ACTIVE without interrupting readers."""
        with self._lock:
            if not self._staging_stage:
                raise RuntimeError("No model currently in STAGING to promote")

            if not self._staging_stage.health_checked:
                raise RuntimeError("Cannot promote model that has not passed health check")

            old_active = self._active_stage
            new_active = self._staging_stage

            # Atomic pointer swap
            self._active_stage = new_active
            self._staging_stage = None

            new_active.state = ModelLifecycleState.ACTIVE
            if old_active is not None:
                old_active.state = ModelLifecycleState.RETIRED

            # Durable lineage manifest append
            self._persist_manifest()

            return new_active.identity

    def rollback_to_generation(self, generation: int) -> ModelIdentity:
        """Rolls back the active model to an earlier compiled generation."""
        with self._lock:
            if generation not in self._stages_by_gen:
                raise ValueError(f"Target rollback generation {generation} is not loaded")

            target_stage = self._stages_by_gen[generation]
            if not target_stage.health_checked:
                raise RuntimeError(f"Target rollback generation {generation} failed health check")

            if self._active_stage is not None:
                self._active_stage.state = ModelLifecycleState.RETIRED

            self._active_stage = target_stage
            target_stage.state = ModelLifecycleState.ACTIVE
            self._staging_stage = None

            self._persist_manifest()
            return target_stage.identity

    def _persist_manifest(self) -> None:
        """Durable atomic write of the lineage manifest to disk."""
        manifest_file = self.model_dir / self.MANIFEST_FILENAME
        tmp_file = manifest_file.with_name(manifest_file.name + ".tmp")

        history: List[Dict[str, Any]] = []
        for gen in sorted(self._stages_by_gen.keys()):
            s = self._stages_by_gen[gen]
            history.append({
                "generation": s.generation,
                "state": s.state.value,
                "model_id": s.identity.model_id,
                "model_version": s.identity.model_version,
                "model_artifact_hash": s.identity.model_artifact_hash,
                "parent_model_hash": s.identity.parent_model_hash,
                "identity_hash": s.identity.identity_hash,
                "compile_latency_ms": s.compile_latency_ms,
                "onnx_relpath": str(s.onnx_path.relative_to(self.model_dir)),
            })

        payload = {
            "active_generation": self._active_stage.generation if self._active_stage else None,
            "active_identity_hash": self._active_stage.identity.identity_hash if self._active_stage else None,
            "device": self.device,
            "history": history,
        }

        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp_file.replace(manifest_file)

    def recover_from_manifest(self) -> Optional[ModelIdentity]:
        """Cold restart recovery: restores the latest active certified model from disk."""
        manifest_file = self.model_dir / self.MANIFEST_FILENAME
        if not manifest_file.exists():
            return None

        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        active_gen = data.get("active_generation")
        if active_gen is None:
            return None

        for item in data.get("history", []):
            gen = int(item["generation"])
            onnx_path = self.model_dir / item["onnx_relpath"]
            if not onnx_path.exists():
                continue

            # Verify artifact SHA-256 integrity
            import hashlib
            with open(onnx_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != item["model_artifact_hash"]:
                raise ValueError(f"Durable model artifact corrupted: {onnx_path}")

            # Recompile
            ov_model = self.core.read_model(str(onnx_path))
            compiled = self.core.compile_model(ov_model, self.device)

            identity = ModelIdentity(
                model_id=item["model_id"],
                model_version=item["model_version"],
                model_artifact_hash=item["model_artifact_hash"],
                training_generation=gen,
                parent_model_hash=item.get("parent_model_hash"),
                metadata={"device": self.device},
            )

            stage = StagedModel(
                generation=gen,
                identity=identity,
                onnx_path=onnx_path,
                compiled_model=compiled,
                state=ModelLifecycleState.RETIRED,
                health_checked=True,
                compile_latency_ms=float(item.get("compile_latency_ms", 0.0)),
            )

            self._stages_by_gen[gen] = stage
            self._stages_by_hash[identity.model_artifact_hash] = stage

            if gen == active_gen:
                stage.state = ModelLifecycleState.ACTIVE
                self._active_stage = stage

        return self._active_stage.identity if self._active_stage else None
