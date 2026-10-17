"""Distributed Runtime, Framing Session, and Physical Peer Transport (WP08).

Supports peer identity, causal sequence validation, replay protection,
and physical serial/socket framing for Workstation, Jetson Nano, and Arduino Uno.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import io
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from uow.protocol.v1 import (
    CausalClock,
    CausalOrderDetector,
    CRCError,
    CorruptMagicError,
    FrameError,
    ProtocolMessage,
    TruncatedFrameError,
    WorkEvent,
    WorkRequest,
    decode_frame,
    encode_frame,
)


class NodeType(str, Enum):
    HOST_COMPLETE = "host_complete"
    EDGE_COMPACT = "edge_compact"
    EDGE_TRANSPORT = "edge_transport"
    ENDPOINT_DETERMINISTIC = "endpoint_deterministic"


@dataclass
class PeerNode:
    node_id: str
    node_type: NodeType
    address: str = "local"
    is_online: bool = True
    clock: CausalClock = field(default_factory=lambda: CausalClock(node_id="unknown"))

    def __post_init__(self):
        if self.clock.node_id == "unknown":
            self.clock = CausalClock(node_id=self.node_id)


class FramedTransportSession:
    """Manages reliable framed protocol message delivery over physical/virtual channels."""

    def __init__(self, local_node: PeerNode) -> None:
        self.local_node = local_node
        self.peers: Dict[str, PeerNode] = {}
        self.replay_detector = CausalOrderDetector()
        self._partitioned_peers: Set[str] = set()  # Simulated or detected network partition
        self._sent_journal: List[bytes] = []
        self._received_journal: List[ProtocolMessage] = []

    def register_peer(self, peer: PeerNode) -> None:
        self.peers[peer.node_id] = peer

    def set_partition(self, peer_id: str, is_partitioned: bool) -> None:
        """Simulate or apply network partition isolation."""
        if is_partitioned:
            self._partitioned_peers.add(peer_id)
        else:
            self._partitioned_peers.discard(peer_id)

    def send_message(self, target_node_id: str, message: ProtocolMessage) -> bytes:
        """Encode message into framed byte stream and send to target peer."""
        if target_node_id in self._partitioned_peers:
            raise FrameError(f"Network partition active: cannot reach peer '{target_node_id}'.")

        seq = self.local_node.clock.tick()
        raw_frame = encode_frame(message, sequence=seq)
        self._sent_journal.append(raw_frame)
        return raw_frame

    def receive_frame(
        self,
        raw_frame: bytes,
        sender_node_id: str,
    ) -> Tuple[ProtocolMessage, int]:
        """Decode and validate an incoming frame from a peer.
        
        Checks:
        1. Network partition status
        2. CRC32 and framing integrity
        3. Sequence monotonicity and replay prevention
        """
        if sender_node_id in self._partitioned_peers:
            raise FrameError(f"Network partition active: frame rejected from '{sender_node_id}'.")

        msg, seq, flags = decode_frame(raw_frame)

        # Replay and duplicate verification
        msg_id = getattr(msg, "event_id", getattr(msg, "work_id", f"msg_{seq}"))
        if self.replay_detector.is_replay_or_duplicate(msg_id, sender_node_id, seq):
            raise FrameError(f"Replay or duplicate detected: event '{msg_id}' from '{sender_node_id}' seq {seq}")

        self.replay_detector.record_processed(msg_id, sender_node_id, seq)
        self.local_node.clock.observe(sender_node_id, seq)
        self._received_journal.append(msg)

        return msg, seq


class ArduinoUnoSerialLink:
    """Emulates or communicates with Arduino Uno serial endpoint.
    
    Exchanges binary framed packets with CRC32 over virtual or hardware COM port.
    """

    def __init__(self, port: str = "COM3", baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate
        self.endpoint_node = PeerNode(
            node_id="uno_endpoint",
            node_type=NodeType.ENDPOINT_DETERMINISTIC,
        )
        self.session = FramedTransportSession(self.endpoint_node)
        self.led_state: bool = False
        self.last_sensor_reading: float = 0.0

    def process_incoming_sensor_frame(self, raw_frame: bytes) -> WorkEvent:
        """Decode sensor telemetry frame received from Uno."""
        msg, seq = self.session.receive_frame(raw_frame, "uno_endpoint")
        if isinstance(msg, WorkEvent):
            self.last_sensor_reading = float(msg.payload.get("sensor_val", 0.0))
            return msg
        raise FrameError(f"Expected WorkEvent from Uno, got {type(msg)}")

    def build_actuation_frame(self, target_led: bool, seq: int) -> bytes:
        """Build framed actuation command to actuate onboard LED/relay."""
        evt = WorkEvent(
            event_id=f"act-uno-{seq}",
            node_id="host_workstation",
            local_sequence=seq,
            local_time_ms=int(time.time() * 1000),
            causal_parents=[],
            event_type="actuate_led",
            payload={"led_on": target_led},
        )
        return encode_frame(evt, sequence=seq)
