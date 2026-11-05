import json
from pathlib import Path
import socket
import threading

from integrations.omarchy_uow.gateway import Gateway
from integrations.omarchy_uow.service import Service


def exchange(path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.sendall((json.dumps(request) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            data += client.recv(4096)
        return json.loads(data)


def test_gateway_authority_receipt_and_restart(tmp_path):
    path = tmp_path / "gateway.sock"
    policy = {"sensor": ["observation.ingest"]}
    tokens = {"secret": "sensor"}
    gateway = Gateway(path, tmp_path / "state.db", policy, tokens)
    thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    thread.start()
    try:
        obs = {"observation_id": "o1", "sensor_id": "sim", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": 1, "modality": "NUMERIC_GAUGE", "reading": {"value": 21, "unit": "C"}, "confidence": 0.5}
        req = {"request_id": "r1", "token": "secret", "kind": "observation.ingest", "payload": obs}
        assert exchange(path, {**req, "token": "wrong"})["decision"] == "DENIED"
        malformed = {**req, "request_id": "bad-unicode", "payload": {**obs, "extra": "\ud800"}}
        assert exchange(path, malformed)["decision"] == "DENIED"
        assert exchange(path, {**req, "request_id": "denied-shell", "kind": "shell.execute"})["decision"] == "DENIED"
        first = exchange(path, req)
        assert first["decision"] == "COMMITTED"
        assert exchange(path, req) == first
    finally:
        gateway.shutdown(); thread.join(timeout=2); gateway.server_close()
    assert not path.exists()
    recovered = Service(tmp_path / "state.db", policy, tokens)
    try:
        assert recovered.state.sequence == 1
        assert recovered.ledger.records[0].record_hash == first["receipt"]["record_hash"]
    finally:
        recovered.close()


def test_gateway_rejects_occupied_path(tmp_path):
    path = tmp_path / "gateway.sock"
    path.write_text("not a socket")
    try:
        try:
            Gateway(path, tmp_path / "state.db", {}, {})
        except FileExistsError:
            pass
        else:
            assert False, "must not overwrite an occupied path"
    finally:
        pass
    assert path.read_text() == "not a socket"
