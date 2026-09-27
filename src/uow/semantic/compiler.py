"""Deterministic native UoW compilation from certified semantic IntentEnvelope."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable, Dict, Iterable, Optional, Protocol, Tuple, runtime_checkable

from .schema import IntentEnvelope
from ..contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, UoW, make_uow
from ..ontology import MatrixCell, WorkCategory
from ..state import WorldState


def derive_semantic_uow_id(
    signal_id: str,
    closure_certificate_hash: str,
    compiler_id: str,
) -> str:
    """Deterministically derive UoW identity from semantic provenance.

    uow_id = "uow-sem-" + SHA256(signal_id || closure_certificate_hash || compiler_id)[:24]
    """
    material = f"{signal_id}:{closure_certificate_hash}:{compiler_id}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"uow-sem-{digest[:24]}"


@runtime_checkable
class SemanticUoWCompiler(Protocol):
    """Protocol for registered deterministic UoW compilers."""

    @property
    def compiler_id(self) -> str:
        ...

    def compile(
        self,
        intent: IntentEnvelope,
        state: WorldState,
    ) -> UoW:
        ...


class TransferUoWCompiler:
    """Deterministic native UoW compiler for transfer/dispatch/convey operations."""

    def __init__(
        self,
        compiler_id: str = "compiler.transfer.v1",
        *,
        preserve_running: bool = True,
    ) -> None:
        self._compiler_id = compiler_id
        self._preserve_running = preserve_running

    @property
    def compiler_id(self) -> str:
        return self._compiler_id

    def compile(
        self,
        intent: IntentEnvelope,
        state: WorldState,
    ) -> UoW:
        b_map = intent.binding_map()
        recipient = str(b_map.get("recipient") or b_map.get("destination") or "UNKNOWN_TARGET")
        raw_qty = b_map.get("quantity", 1)
        if isinstance(raw_qty, str) and raw_qty.upper() in ("ALL", "UNIVERSAL"):
            qty = int(state.attributes.get("available_inventory", 100))
        else:
            try:
                qty = int(raw_qty)
            except Exception:
                qty = 1

        uow_id = derive_semantic_uow_id(
            intent.signal_id,
            intent.closure_certificate_hash,
            self.compiler_id,
        )

        guard = Guard(GuardOp.ALWAYS)
        mutations = (
            Mutation(MutationOp.SET, f"transfers.{recipient}", qty),
            Mutation(MutationOp.SET, f"transfers.{recipient}.signal_id", intent.signal_id),
        )

        successor = Successor.preserve() if self._preserve_running else Successor.halt()
        routes = (
            Route(
                guard=guard,
                mutations=mutations,
                successor=successor,
            ),
        )

        return make_uow(
            identity=uow_id,
            routes=routes,
            matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
            layer="semantic-h4",
            parent_context=f"semantic:{intent.closure_certificate_hash}",
        )


class PurgeUoWCompiler:
    """Deterministic native UoW compiler for purge/disgorge/clean operations."""

    def __init__(
        self,
        compiler_id: str = "compiler.purge.v1",
        *,
        preserve_running: bool = True,
    ) -> None:
        self._compiler_id = compiler_id
        self._preserve_running = preserve_running

    @property
    def compiler_id(self) -> str:
        return self._compiler_id

    def compile(
        self,
        intent: IntentEnvelope,
        state: WorldState,
    ) -> UoW:
        b_map = intent.binding_map()
        target = str(b_map.get("destination") or b_map.get("target") or "SECTOR_DEFAULT")

        uow_id = derive_semantic_uow_id(
            intent.signal_id,
            intent.closure_certificate_hash,
            self.compiler_id,
        )

        guard = Guard(GuardOp.ALWAYS)
        mutations = (
            Mutation(MutationOp.SET, f"purged.{target}", True),
            Mutation(MutationOp.SET, f"purged.{target}.signal_id", intent.signal_id),
        )

        successor = Successor.preserve() if self._preserve_running else Successor.halt()
        routes = (
            Route(
                guard=guard,
                mutations=mutations,
                successor=successor,
            ),
        )

        return make_uow(
            identity=uow_id,
            routes=routes,
            matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
            layer="semantic-h4",
            parent_context=f"semantic:{intent.closure_certificate_hash}",
        )


class SemanticCompilerRegistry:
    """Deterministic registry mapping qualified operators to semantic compilers."""

    def __init__(self) -> None:
        self._compilers: dict[str, SemanticUoWCompiler] = {}
        # Pre-register default operational compilers
        transfer_compiler = TransferUoWCompiler()
        purge_compiler = PurgeUoWCompiler()
        for op in ("transfer", "dispatch", "convey", "allocate", "consign", "deliver", "send"):
            self.register(op, transfer_compiler)
        for op in ("purge", "disgorge", "clean"):
            self.register(op, purge_compiler)

    @property
    def compiler_id(self) -> str:
        return "registry.semantic.v1"

    def register(self, operator: str, compiler: SemanticUoWCompiler) -> None:
        self._compilers[operator.lower()] = compiler

    def get(self, operator: str) -> Optional[SemanticUoWCompiler]:
        return self._compilers.get(operator.lower())

    def resolve(self, intent: IntentEnvelope) -> SemanticUoWCompiler:
        b_map = intent.binding_map()
        operator = b_map.get("operator") or b_map.get("operation") or b_map.get("semantic_head")
        if not operator:
            # Fallback to transfer if recipient is specified
            if "recipient" in b_map or "destination" in b_map:
                operator = "transfer"
            else:
                raise ValueError(f"Intent missing operator in binding map: {b_map}")

        compiler = self.get(str(operator))
        if compiler is None:
            raise KeyError(f"No registered SemanticUoWCompiler for operator {operator!r}")
        return compiler

    def compile(
        self,
        intent: IntentEnvelope,
        state: WorldState,
    ) -> UoW:
        compiler = self.resolve(intent)
        return compiler.compile(intent, state)
