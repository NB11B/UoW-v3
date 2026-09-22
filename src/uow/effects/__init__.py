"""Public API for Pass 4: External Effects & Sagas."""
from .certification import (
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from .descriptor import (
    CompensationSpec,
    EffectDescriptor,
    EffectReceipt,
    EffectStatus,
    compute_idempotency_key,
    create_effect_descriptor,
)
from .runner import (
    EFFECT_CELL,
    EffectRunner,
    ExternalClientProtocol,
    MockExternalClient,
    ORCH_EFFECTS_KEY,
    get_effects_map,
)
from .saga import (
    ORCH_COMPENSATION_FAILED_KEY,
    SagaCompensationError,
    SagaCoordinator,
    SagaStep,
)

__all__ = [
    "CompensationSpec",
    "EFFECT_CELL",
    "EffectDescriptor",
    "EffectReceipt",
    "EffectRunner",
    "EffectStatus",
    "ExternalClientProtocol",
    "MockExternalClient",
    "ORCH_COMPENSATION_FAILED_KEY",
    "ORCH_EFFECTS_KEY",
    "SagaCompensationError",
    "SagaCoordinator",
    "SagaStep",
    "compute_idempotency_key",
    "create_effect_descriptor",
    "get_effects_map",
    "verify_effect_intent_binding",
    "verify_effect_receipt_binding",
]
