"""Host-only narrow containment check; opt in with UOW_RUN_HOST_SANDBOX_TEST=1."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from integrations.omarchy_uow.gateway import Gateway


@pytest.mark.skipif(os.environ.get("UOW_RUN_HOST_SANDBOX_TEST") != "1" or not shutil.which("bwrap"), reason="requires host Bubblewrap access")
def test_restricted_client_can_use_gateway_but_cannot_see_host_state(tmp_path):
    socket_dir = tmp_path / "socket"
    socket_dir.mkdir(mode=0o700)
    db_dir = tmp_path / "private"
    db_dir.mkdir(mode=0o700)
    gateway = Gateway(socket_dir / "uow.sock", db_dir / "state.db", {"sensor": ["observation.ingest"]}, {"scoped-token": "sensor"})
    thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    thread.start()
    client = r'''
import json, pathlib, socket
assert not pathlib.Path('/home').exists()
assert not pathlib.Path('/run/uow/state.db').exists()
assert not pathlib.Path('/run/uow/../private/state.db').exists()
obs={'observation_id':'isolated-1','sensor_id':'sandbox-sim','sensor_type':'ENVIRONMENTAL_PROBE','causal_epoch':1,'modality':'NUMERIC_GAUGE','reading':{'value':20,'unit':'C'},'confidence':0.5}
with socket.socket(socket.AF_UNIX) as s:
 s.connect('/run/uow/uow.sock')
 s.sendall((json.dumps({'request_id':'isolated-1','token':'scoped-token','kind':'observation.ingest','payload':obs})+'\n').encode())
 response=json.loads(s.makefile().readline())
 assert response['decision']=='COMMITTED', response
 print(response['receipt']['record_hash'])
'''
    try:
        result = subprocess.run([
            "bwrap", "--unshare-all", "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--dir", "/run", "--ro-bind", str(socket_dir), "/run/uow",
            "--chdir", "/tmp", "/usr/bin/python3", "-c", client,
        ], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert len(result.stdout.strip()) == 64
    finally:
        gateway.shutdown(); thread.join(timeout=2); gateway.server_close()
    assert db_dir.joinpath("state.db").exists()
