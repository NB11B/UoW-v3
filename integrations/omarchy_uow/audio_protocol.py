"""Fixed ESP32 audio and telemetry wire profile. No capture or network side effects."""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct
import subprocess

TARGET = "192.168.254.75"
AUDIO_PORT = 4000
TELEMETRY_PORT = 4002
FRAMES = 256
PAYLOAD_BYTES = FRAMES * 2 * 2


def encode_audio(sequence: int, timestamp: int, pcm: bytes) -> bytes:
    if type(sequence) is not int or not 0 <= sequence < 2**64 or type(timestamp) is not int or not 0 <= timestamp < 2**64 or len(pcm) != PAYLOAD_BYTES:
        raise ValueError("AUDIO_PACKET")
    return struct.pack("<IHQQ", 0x41504455, 1, sequence, timestamp) + pcm


@dataclass(frozen=True)
class Telemetry:
    sequence: int
    timestamp_ms: int
    low_hz: float
    high_hz: float
    drops: int
    out_of_order: int
    underruns: int
    overruns: int


class ReceiverEpoch:
    def __init__(self):
        self.sequence = None

    def reset(self):
        self.sequence = None


def parse_telemetry(packet: bytes, sender: tuple[str, int], epoch: ReceiverEpoch) -> Telemetry | None:
    # Firmware creates a new UDP socket for each report, so its source port is ephemeral.
    if sender[0] != TARGET or len(packet) != 184:
        return None
    magic, version, size, sequence, timestamp = struct.unpack_from("<IHHII", packet)
    if (magic, version, size) != (0x4D544352, 1, 184):
        return None
    if epoch.sequence is not None and sequence <= epoch.sequence:
        return None
    low, high = struct.unpack_from("<ff", packet, 44)
    if not math.isfinite(low) or not math.isfinite(high) or not 0 <= low < high <= 24000:
        return None
    drops, ooo, underruns, overruns = struct.unpack_from("<IIII", packet, 160)
    epoch.sequence = sequence
    return Telemetry(sequence, timestamp, low, high, drops, ooo, underruns, overruns)


def _run(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, timeout=3)


def default_monitor(run=_run) -> str:
    sink = run(["pactl", "get-default-sink"]).strip()
    if not sink or "\n" in sink or "\t" in sink or sink.endswith(".monitor"):
        raise ValueError("DEFAULT_SINK_INVALID")
    monitor = sink + ".monitor"
    sources = run(["pactl", "list", "short", "sources"])
    if monitor not in [fields[1] for line in sources.splitlines() if len(fields := line.split("\t")) >= 2]:
        raise ValueError("DEFAULT_MONITOR_MISSING")
    return monitor
