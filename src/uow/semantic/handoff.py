"""Lower certified semantic intent into the native UoW contract API."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from .schema import IntentEnvelope, SemanticDisposition, SemanticResult
from ..contracts import Route, UoW, make_uow
from ..ontology import MatrixCell, WorkCategory


RouteBuilder = Callable[[IntentEnvelope], Iterable[Route]]


class SemanticHandoff:
    """Create native UoW proposal material from semantic YES only.

    This class intentionally does not expose commit(), execute(), or any
    authority operation. Once a UoW is constructed, the existing application
    spine owns PROPOSE -> CERTIFY -> COMMIT.
    """

    def to_uow(
        self,
        result: SemanticResult,
        *,
        uow_id: str,
        route_builder: RouteBuilder,
        matrix_cell: MatrixCell = MatrixCell(
            WorkCategory.PROCESSES,
            WorkCategory.DATA,
        ),
    ) -> UoW:
        if result.disposition is not SemanticDisposition.YES or result.intent is None:
            raise ValueError("Only semantic YES may be lowered into native UoW material.")

        routes = tuple(route_builder(result.intent))
        if not routes:
            raise ValueError("Semantic UoW lowering requires at least one deterministic route.")

        return make_uow(
            identity=uow_id,
            routes=routes,
            matrix_cell=matrix_cell,
            layer="semantic-handoff",
            parent_context=f"semantic:{result.certificate.certificate_hash}",
        )
