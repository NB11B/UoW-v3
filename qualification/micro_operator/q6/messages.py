"""Q6 Wire Protocol: Length-prefixed framing and message schemas for socket communication."""
from __future__ import annotations

import json
import socket
import struct
from typing import Any, Dict, Optional

HEADER_FORMAT = ">I"  # 4-byte unsigned int big-endian
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_SIZE = 16 * 1024 * 1024  # 16 MB max frame

def send_frame(sock: socket.socket, data: Dict[str, Any]) -> None:
    raw_payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    if len(raw_payload) > MAX_MESSAGE_SIZE:
        raise ValueError(f"Payload size {len(raw_payload)} exceeds maximum frame limit.")
    header = struct.pack(HEADER_FORMAT, len(raw_payload))
    sock.sendall(header + raw_payload)

def recv_frame(sock: socket.socket, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    if timeout is not None:
        sock.settimeout(timeout)
    # Read header
    header_bytes = b""
    while len(header_bytes) < HEADER_SIZE:
        chunk = sock.recv(HEADER_SIZE - len(header_bytes))
        if not chunk:
            return None
        header_bytes += chunk

    payload_len = struct.unpack(HEADER_FORMAT, header_bytes)[0]
    if payload_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"Incoming payload size {payload_len} exceeds maximum frame limit.")

    # Read payload
    payload_bytes = bytearray()
    while len(payload_bytes) < payload_len:
        chunk = sock.recv(min(4096, payload_len - len(payload_bytes)))
        if not chunk:
            return None
        payload_bytes.extend(chunk)

    return json.loads(payload_bytes.decode("utf-8"))
