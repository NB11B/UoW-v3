from __future__ import annotations

import inspect

import uow
from uow.composition import AdversarialChannel, WireEnvelope, sign_envelope, verify_envelope
from uow.realizations.network.wire import (
    AdversarialChannel as ImplChannel,
    WireEnvelope as ImplEnvelope,
    sign_envelope as impl_sign,
    verify_envelope as impl_verify,
)


def test_s4_wire_imports_remain_identity_compatible():
    assert AdversarialChannel is ImplChannel
    assert WireEnvelope is ImplEnvelope
    assert sign_envelope is impl_sign
    assert verify_envelope is impl_verify

    assert uow.AdversarialChannel is ImplChannel
    assert uow.WireEnvelope is ImplEnvelope


def test_s4_historical_wire_module_is_only_compatibility_shim():
    import uow.composition.wire as shim

    source = inspect.getsource(shim)
    assert "class WireEnvelope" not in source
    assert "class AdversarialChannel" not in source
    assert "realizations.network.wire" in source


def test_s4_relocated_wire_behavior_preserves_sign_verify_and_faults():
    env = ImplEnvelope(
        sender_id="A",
        recipient_id="B",
        seq=1,
        epoch=2,
        nonce="n",
        payload={"x": 1},
    )
    signed = impl_sign("secret", env)
    assert impl_verify("secret", signed)
    assert not impl_verify("wrong", signed)

    channel = ImplChannel(loss_rate=0.0, duplication_rate=1.0, reorder=False, seed=1)
    delivered = channel.transmit(signed)
    assert delivered == [signed, signed]

    channel.set_asymmetric_drop("A", "B", True)
    assert channel.transmit(signed) == []
