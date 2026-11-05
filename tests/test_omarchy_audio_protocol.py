import struct
import unittest

from integrations.omarchy_uow.audio_protocol import encode_audio, parse_telemetry, ReceiverEpoch, default_monitor


def packet(seq=7, low=100.0, high=2500.0):
    b = bytearray(184)
    struct.pack_into("<IHHII", b, 0, 0x4D544352, 1, 184, seq, 1234)
    struct.pack_into("<ff", b, 44, low, high)
    struct.pack_into("<IIII", b, 160, 2, 3, 4, 5)
    return bytes(b)


class ProtocolTests(unittest.TestCase):
    def test_audio_packet_exact_wire_format(self):
        payload = bytes(1024)
        wire = encode_audio(5, 123, payload)
        self.assertEqual(len(wire), 1046)
        self.assertEqual(struct.unpack_from("<IHQQ", wire), (0x41504455, 1, 5, 123))
        with self.assertRaises(ValueError):
            encode_audio(5, 123, b"short")

    def test_telemetry_shape_source_and_sequence(self):
        epoch = ReceiverEpoch()
        self.assertIsNone(parse_telemetry(packet(), ("192.168.254.99", 4002), epoch))
        self.assertIsNone(parse_telemetry(packet()[:-1], ("192.168.254.75", 4002), epoch))
        first = parse_telemetry(packet(), ("192.168.254.75", 4002), epoch)
        self.assertEqual((first.low_hz, first.high_hz, first.drops, first.underruns), (100, 2500, 2, 4))
        self.assertIsNone(parse_telemetry(packet(), ("192.168.254.75", 4002), epoch))
        epoch.reset()
        self.assertIsNotNone(parse_telemetry(packet(1), ("192.168.254.75", 55321), epoch))

    def test_default_monitor_never_microphone(self):
        calls = []
        def run(args):
            calls.append(args)
            if args == ["pactl", "get-default-sink"]:
                return "alsa_output.pci-speakers\n"
            return "1\talsa_input.mic\tPipeWire\n2\talsa_output.pci-speakers.monitor\tPipeWire\n"
        self.assertEqual(default_monitor(run), "alsa_output.pci-speakers.monitor")
        self.assertEqual(calls[1], ["pactl", "list", "short", "sources"])
        with self.assertRaises(ValueError):
            default_monitor(lambda args: "alsa_output.pci-speakers\n" if "get-default" in args else "1\talsa_input.mic\tPipeWire\n")


if __name__ == "__main__":
    unittest.main()
