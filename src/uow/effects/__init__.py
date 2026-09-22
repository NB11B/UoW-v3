"""Public API for Pass 4: External Effects & Sagas."""
from .certification import (
    HMACReceiptAuthenticator,
    PrefixReceiptAuthenticator,
    ReceiptAuthenticator,
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from .descriptor import (
    LEGAL_EFFECT_TRANSITIONS,
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
    ORCH_SAGAS_KEY,
    SagaCompensationError,
    SagaCoordinator,
    SagaRecord,
    SagaStatus,
    SagaStep,
    get_sagas_map,
)

__all__ = [
    "CompensationSpec",
    "EFFECT_CELL",
    "EffectDescriptor",
    "EffectReceipt",
    "EffectRunner",
    "EffectStatus",
    "ExternalClientProtocol",
    "HMACReceiptAuthenticator",
    "LEGAL_EFFECT_TRANSITIONS",
    "MockExternalClient",
    "ORCH_COMPENSATION_FAILED_KEY",
    "ORCH_EFFECTS_KEY",
    "ORCH_SAGAS_KEY",
    "PrefixReceiptAuthenticator",
    "ReceiptAuthenticator",
    "SagaCompensationError",
    "SagaCoordinator",
    "SagaRecord",
    "SagaStatus",
    "SagaStep",
    "compute_idempotency_key",
    "create_effect_descriptor",
    "get_effects_map",
    "get_sagas_map",
    "verify_effect_intent_binding",
    "verify_effect_receipt_binding",
]
