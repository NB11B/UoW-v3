"""Physical and Serial Transport Framing Protocol.

Implements binary framing with magic prefix, sequence numbers, length headers,
and CRC32 error detection for physical links (e.g. Arduino Uno serial, socket transport).
"""
from __future__ import annotations

import json
import struct
import zlib
from typing import Tuple, Dict, Any, Type, Optional

from .canonical import canonical_json
from .messages import (
    ProtocolMessage,
    WorkRequest,
    CapabilityDescriptor,
    CapabilityProposal,
    WorkCertificate,
    CommitRecord,
    WorkEvent,
    RecoveryCommand,
    CapabilityPackageManifest,
)

MAGIC_BYTES = b"UOW1"  # 4 bytes
HEADER_FORMAT = ">4sBBHII"  # Magic(4), Version(1), MsgType(1), Flags(2), Seq(4), Length(4) = 16 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FOOTER_FORMAT = ">I"  # CRC32 (4 bytes)
FOOTER_SIZE = struct.calcsize(FOOTER_FORMAT)

MSG_TYPE_MAP: Dict[int, Type[ProtocolMessage]] = {
    0x01: WorkRequest,
    0x02: CapabilityDescriptor,
    0x03: CapabilityProposal,
    0x04: WorkCertificate,
    0x05: CommitRecord,
    0x06: WorkEvent,
    0x07: RecoveryCommand,
    0x08: CapabilityPackageManifest,
}
TYPE_TO_ID_MAP = {cls: msg_id for msg_id, cls in MSG_TYPE_MAP.items()}


class FrameError(Exception):
    """Base exception for transport framing errors."""
    pass


class CorruptMagicError(FrameError):
    """Raised when framing magic bytes do not match 'UOW1'."""
    pass


class CRCError(FrameError):
    """Raised when frame CRC32 integrity check fails."""
    pass


class TruncatedFrameError(FrameError):
    """Raised when raw frame has fewer bytes than declared length."""
    pass


def encode_frame(
    message: ProtocolMessage,
    sequence: int = 0,
    flags: int = 0,
    version: int = 1,
) -> bytes:
    """Encode a ProtocolMessage into a framed byte stream with CRC32 verification."""
    msg_type = TYPE_TO_ID_MAP.get(type(message), 0x00)
    if msg_type == 0x00:
        raise FrameError(f"Unsupported message type for framing: {type(message)}")

    payload_str = message.to_canonical_json()
    payload_bytes = payload_str.encode("utf-8")
    payload_len = len(payload_bytes)

    header = struct.pack(
        HEADER_FORMAT,
        MAGIC_BYTES,
        version,
        msg_type,
        flags,
        sequence,
        payload_len,
    )
    # CRC32 computed across Header + Payload
    crc = zlib.crc32(header + payload_bytes) & 0xFFFFFFFF
    footer = struct.pack(FOOTER_FORMAT, crc)

    return header + payload_bytes + footer


def decode_frame(raw_bytes: bytes) -> Tuple[ProtocolMessage, int, int]:
    """Decode a raw byte stream into a ProtocolMessage.
    
    Returns:
        (message, sequence, flags)
    """
    if len(raw_bytes) < HEADER_SIZE + FOOTER_SIZE:
        raise TruncatedFrameError(f"Frame length {len(raw_bytes)} is below minimum required header+footer.")

    magic, version, msg_type, flags, sequence, payload_len = struct.unpack_from(HEADER_FORMAT, raw_bytes, 0)
    if magic != MAGIC_BYTES:
        raise CorruptMagicError(f"Invalid frame magic: {magic!r}, expected {MAGIC_BYTES!r}")

    expected_total_len = HEADER_SIZE + payload_len + FOOTER_SIZE
    if len(raw_bytes) < expected_total_len:
        raise TruncatedFrameError(
            f"Frame payload truncated: expected {expected_total_len} bytes, got {len(raw_bytes)}."
        )

    payload_bytes = raw_bytes[HEADER_SIZE : HEADER_SIZE + payload_len]
    expected_crc = struct.unpack_from(FOOTER_FORMAT, raw_bytes, HEADER_SIZE + payload_len)[0]

    actual_crc = zlib.crc32(raw_bytes[: HEADER_SIZE + payload_len]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise CRCError(f"Frame CRC mismatch: calculated {actual_crc:#010x}, received {expected_crc:#010x}")

    msg_cls = MSG_TYPE_MAP.get(msg_type)
    if msg_cls is None:
        raise FrameError(f"Unknown message type code {msg_type:#04x}")

    try:
        data = json.loads(payload_bytes.decode("utf-8"))
        msg = msg_cls(**data)
        return msg, sequence, flags
    except Exception as e:
        raise FrameError(f"Failed to instantiate message {msg_cls.__name__}: {e}") from e
