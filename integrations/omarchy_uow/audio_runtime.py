"""Local-only audio worker process and fixed Unix control commands."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import time
import uuid

from .audio_protocol import TARGET, AUDIO_PORT, TELEMETRY_PORT, default_monitor
from .audio_worker import AudioWorker


class SocketUoW:
    def __init__(self, path: Path, operator_token: str, worker_token: str):
        self.path, self.operator_token, self.worker_token = path, operator_token, worker_token

    def __call__(self, kind, payload):
        token = self.worker_token if kind in {"audio.effect.record", "audio.telemetry.ingest"} else self.operator_token
        request = {"request_id": uuid.uuid4().hex, "token": token, "kind": kind, "payload": payload}
        with socket.socket(socket.AF_UNIX) as conn:
            conn.settimeout(2)
            conn.connect(str(self.path))
            conn.sendall((json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n").encode())
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk or len(data) + len(chunk) > 65536:
                    raise ValueError("UOW_RESPONSE")
                data.extend(chunk)
        return json.loads(data)


def load_preference(path: Path) -> bool:
    if not path.exists():
        return True
    value = json.loads(path.read_text())
    if type(value) is not dict or type(value.get("enabled")) is not bool or set(value) != {"enabled"}:
        raise ValueError("AUDIO_PREFERENCE")
    return value["enabled"]


def save_preference(path: Path, enabled: bool):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x") as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump({"enabled": enabled}, file)
            file.flush(); os.fsync(file.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class UDPTransport:
    def __init__(self):
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.bind(("", TELEMETRY_PORT))
        self.rx.setblocking(False)

    def send(self, data):
        self.tx.sendto(data, (TARGET, AUDIO_PORT))

    def receive(self):
        try:
            return self.rx.recvfrom(2048)
        except BlockingIOError:
            return None

    def close(self):
        self.tx.close(); self.rx.close()


class ParecCapture:
    def __init__(self, monitor):
        self.process = subprocess.Popen(["/usr/bin/parec", "--raw", "--device", monitor, "--format=s16le", "--rate=48000", "--channels=2"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer = bytearray()

    def read(self):
        if len(self.buffer) < 1024:
            try:
                self.buffer.extend(os.read(self.process.stdout.fileno(), 8192))
            except BlockingIOError:
                pass
        # Keep at most 48 ms of the newest playback if a receiver or receipt
        # call briefly delays the sender. Do not allow latency or memory to grow.
        if len(self.buffer) > 9216:
            discard = ((len(self.buffer) - 9216 + 1023) // 1024) * 1024
            del self.buffer[:discard]
            self.dropped_packets = getattr(self, "dropped_packets", 0) + discard // 1024
        if self.process.poll() is not None and len(self.buffer) < 1024:
            raise OSError("CAPTURE_EXITED")
        if len(self.buffer) < 1024:
            return None
        data = bytes(self.buffer[:1024]); del self.buffer[:1024]
        return data

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=1)
        self.process.stdout.close()


def runtime_paths():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omarchy-uow-audio"
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy-uow-audio"
    return runtime, state


def serve(args):
    runtime, state = runtime_paths()
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_file = (runtime / "worker.lock").open("a+")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 2
    control_path = runtime / "worker.sock"
    if control_path.exists():
        if not stat.S_ISSOCK(control_path.lstat().st_mode):
            raise FileExistsError(control_path)
        control_path.unlink()
    preference = state / "enabled.json"
    transport = UDPTransport()
    uow = SocketUoW(args.gateway, args.operator_token.read_text().strip(), args.worker_token.read_text().strip())
    monitor_cache = {"name": None, "checked": 0.0}
    def current_monitor():
        now = time.monotonic()
        if monitor_cache["name"] is None or now - monitor_cache["checked"] >= 1:
            monitor_cache["name"] = default_monitor()
            monitor_cache["checked"] = now
        return monitor_cache["name"]
    worker = AudioWorker(current_monitor, ParecCapture, transport, uow)
    worker.desired = load_preference(preference)
    with socket.socket(socket.AF_UNIX) as server:
        old_umask = os.umask(0o077)
        try:
            server.bind(str(control_path))
        finally:
            os.umask(old_umask)
        server.listen(4)
        server.settimeout(0.001)
        try:
            while True:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    conn = None
                if conn is not None:
                    with conn:
                        conn.settimeout(0.2)
                        try:
                            command = conn.recv(128).decode().strip()
                            if command == "heartbeat":
                                worker.heartbeat()
                            elif command == "on":
                                save_preference(preference, True); worker.on(); worker.heartbeat()
                            elif command == "off":
                                save_preference(preference, False); worker.off()
                            elif command != "status":
                                raise ValueError("CONTROL_COMMAND")
                            result = worker.status() | {"enabled": worker.desired}
                        except (ValueError, UnicodeError, OSError):
                            result = {"state": "error"}
                        conn.sendall((json.dumps(result) + "\n").encode())
                try:
                    worker.step()
                except (OSError, ValueError):
                    worker._close("INTERRUPTED", stop_intent=True)
                    worker.mode = "error"
                    worker.retry_after = time.monotonic() + 1
        finally:
            worker.off()
            transport.close()
            control_path.unlink(missing_ok=True)


def control(command):
    runtime, _ = runtime_paths()
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(2)
        conn.connect(str(runtime / "worker.sock"))
        conn.sendall((command + "\n").encode())
        data = conn.recv(4096)
    print(data.decode().strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--gateway", type=Path, required=True)
    server.add_argument("--operator-token", type=Path, required=True)
    server.add_argument("--worker-token", type=Path, required=True)
    for name in ("heartbeat", "status", "on", "off"):
        sub.add_parser(name)
    args = parser.parse_args()
    if args.command == "serve":
        for file in (args.operator_token, args.worker_token):
            if file.stat().st_mode & 0o077:
                parser.error("token files must have mode 0600")
        return serve(args)
    control(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
