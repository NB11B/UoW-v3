from __future__ import annotations

import inspect

import uow
from uow.effects import (
    SagaCompensationError,
    SagaCoordinator,
    SagaRecord,
    SagaStatus,
    SagaStep,
    get_sagas_map,
)
from uow.implementations.effects.saga import (
    SagaCompensationError as ImplError,
    SagaCoordinator as ImplCoordinator,
    SagaRecord as ImplRecord,
    SagaStatus as ImplStatus,
    SagaStep as ImplStep,
    get_sagas_map as impl_get_sagas_map,
)


def test_s4_saga_imports_remain_identity_compatible():
    assert SagaCoordinator is ImplCoordinator
    assert SagaCompensationError is ImplError
    assert SagaRecord is ImplRecord
    assert SagaStatus is ImplStatus
    assert SagaStep is ImplStep
    assert get_sagas_map is impl_get_sagas_map

    assert uow.SagaCoordinator is ImplCoordinator
    assert uow.SagaStatus is ImplStatus


def test_s4_historical_saga_module_is_only_compatibility_shim():
    import uow.effects.saga as shim

    source = inspect.getsource(shim)
    assert "class SagaCoordinator" not in source
    assert "class SagaRecord" not in source
    assert "implementations.effects.saga" in source


def test_s4_relocated_saga_implementation_has_no_implementation_engine_dependency():
    import uow.implementations.effects.saga as implementation

    source = inspect.getsource(implementation)
    assert "from ..engine" not in source
    assert "from ...engine" in source
