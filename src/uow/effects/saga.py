"""Saga orchestration and reverse-order compensation for Pass 4."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, List, Mapping, Optional, Sequence

from ..contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from ..engine import CertificateResult, Proposal, certify, propose
from ..state import WorldState
from ..transactions import create_transaction_descriptor
from .descriptor import CompensationSpec, EffectDescriptor, EffectStatus
from .runner import (
    EFFECT_CELL,
    EffectRunner,
    ORCH_EFFECTS_KEY,
    get_effects_map,
)

ORCH_COMPENSATION_FAILED_KEY = "__compensation_failed__"


class SagaCompensationError(Exception):
    """Raised when one or more compensation actions fail, retaining unresolved state."""

    def __init__(self, message: str, unresolved_effects: List[EffectDescriptor]) -> None:
        super().__init__(message)
        self.unresolved_effects = unresolved_effects


@dataclass(frozen=True)
class SagaStep:
    """A single step in a multi-step Saga."""

    name: str
    build_effect: Callable[[WorldState], EffectDescriptor]


class SagaCoordinator:
    """Orchestrates multi-step distributed sagas with reverse-order compensation."""

    def __init__(self, runner: EffectRunner) -> None:
        self.runner = runner

    def execute_saga(self, steps: Sequence[SagaStep]) -> List[EffectDescriptor]:
        """Executes saga steps in forward order; on failure, triggers reverse compensation."""
        executed: List[EffectDescriptor] = []

        for step in steps:
            try:
                curr_state = self.runner.sequencer.current_state
                effect = step.build_effect(curr_state)
                res = self.runner.execute_effect(effect)
                executed.append(res)
            except Exception as exc:
                self.compensate(executed, root_cause=exc)
                raise exc

        return executed

    def compensate(
        self,
        executed: Sequence[EffectDescriptor],
        *,
        root_cause: Optional[Exception] = None,
    ) -> List[EffectDescriptor]:
        """Compensates executed effects in strict reverse order [F_n, ..., F_1]."""
        compensated_list: List[EffectDescriptor] = []
        unresolved: List[EffectDescriptor] = []

        for eff in reversed(executed):
            if not eff.compensation:
                continue

            comp_spec = eff.compensation
            comp_effect = replace(
                eff,
                status=EffectStatus.COMPENSATING,
            )

            # Record COMPENSATING status
            curr_state = self.runner.sequencer.current_state
            eff_map = get_effects_map(curr_state)
            eff_map[eff.effect_id] = comp_effect
            serialized = {k: v.to_dict() for k, v in eff_map.items()}

            uow_id = f"compensate_intent::{eff.effect_id}"
            uow = make_uow(
                identity=uow_id,
                routes=[
                    Route(
                        guard=Guard(GuardOp.ALWAYS),
                        mutations=(Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized),),
                        successor=Successor.halt(),
                    )
                ],
                matrix_cell=EFFECT_CELL,
                parent_context="effects",
            )
            prop = propose(uow, curr_state)
            tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_EFFECTS_KEY,))
            cert = certify(uow, curr_state, prop)
            self.runner.sequencer.commit(uow, prop, tx, cert)

            # Invoke external compensation
            try:
                comp_req = dict(comp_spec.request)
                comp_req["effect_id"] = eff.effect_id
                comp_req["is_compensation"] = True
                comp_rcpt = self.runner.client.invoke(comp_req, comp_spec.idempotency_key)

                # Certify and commit COMPENSATED
                comp_final = replace(
                    eff,
                    status=EffectStatus.COMPENSATED,
                    receipt=comp_rcpt,
                )
                curr_state = self.runner.sequencer.current_state
                eff_map = get_effects_map(curr_state)
                eff_map[eff.effect_id] = comp_final
                serialized = {k: v.to_dict() for k, v in eff_map.items()}

                uow_id = f"compensate_done::{eff.effect_id}"
                uow = make_uow(
                    identity=uow_id,
                    routes=[
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized),),
                            successor=Successor.halt(),
                        )
                    ],
                    matrix_cell=EFFECT_CELL,
                    parent_context="effects",
                )
                prop = propose(uow, curr_state)
                tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_EFFECTS_KEY,))
                cert = certify(uow, curr_state, prop)
                self.runner.sequencer.commit(uow, prop, tx, cert)
                compensated_list.append(comp_final)

            except Exception as comp_err:
                # Invariant: Compensation failure MUST NOT be dropped silently
                failed_eff = replace(
                    eff,
                    status=EffectStatus.COMPENSATION_FAILED,
                )
                unresolved.append(failed_eff)

                curr_state = self.runner.sequencer.current_state
                eff_map = get_effects_map(curr_state)
                eff_map[eff.effect_id] = failed_eff
                serialized = {k: v.to_dict() for k, v in eff_map.items()}

                # Record in unresolved state list for operator review
                failed_list = list(curr_state.attributes.get(ORCH_COMPENSATION_FAILED_KEY, ()))
                failed_list.append(failed_eff.to_dict())

                uow_id = f"compensate_failed::{eff.effect_id}"
                uow = make_uow(
                    identity=uow_id,
                    routes=[
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(
                                Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized),
                                Mutation(MutationOp.SET, ORCH_COMPENSATION_FAILED_KEY, failed_list),
                            ),
                            successor=Successor.halt(),
                        )
                    ],
                    matrix_cell=EFFECT_CELL,
                    parent_context="effects",
                )
                prop = propose(uow, curr_state)
                tx = create_transaction_descriptor(
                    uow,
                    curr_state,
                    write_set=(ORCH_EFFECTS_KEY, ORCH_COMPENSATION_FAILED_KEY),
                )
                cert = certify(uow, curr_state, prop)
                self.runner.sequencer.commit(uow, prop, tx, cert)

        if unresolved:
            raise SagaCompensationError(
                f"Saga compensation failed for {len(unresolved)} effect(s). State retained.",
                unresolved_effects=unresolved,
            )

        return compensated_list
