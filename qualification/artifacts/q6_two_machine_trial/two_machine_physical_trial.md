# Two-Machine Physical Qualification Trial: Q6 Distributed Group Commitment

## Executive Summary

- **Repository Baseline**: `NB11B/UoW-v3` at commit `829a050`
- **Machine 1 (Host)**: Windows 11 x86_64 (`192.168.55.100`) — Coordinator, Node A, Node B
- **Machine 2 (Target)**: NVIDIA Jetson Nano ARMv8 Cortex-A57 (`192.168.55.1`) — Node C
- **Physical Interconnect**: USB/RNDIS Virtual Ethernet link (`192.168.55.100` <-> `192.168.55.1`)
- **Link Latency (RTT)**: Min **0.4 ms** | Avg **0.7 ms** | Max **1.1 ms**
- **Timestamp**: 2026-10-16T02:16:23Z
- **Final Verdict**: **`PASS`**

---

## 1. Physical Deployment Topology & Network Characteristics

```
 +-------------------------------------------------------+         +---------------------------------------+
 |                    Machine 1 (Host)                   |         |        Machine 2 (Jetson Nano)        |
 |                     192.168.55.100                    |         |             192.168.55.1              |
 |                                                       |         |                                       |
 |   +-----------------+         +-------------------+   |         |         +-------------------+         |
 |   |  Q6Coordinator  |         | Authority Node A  |   |         |         | Authority Node C  |         |
 |   |    (Client)     |         |   (Port 19201)    |   |         |         |   (Port 19203)    |         |
 |   +--------+--------+         +---------+---------+   |         |         +---------+---------+         |
 |            |                            |             |         |                   |                   |
 |            +--------------+-------------+             |         |                   |                   |
 |                           |                           |         |                   |                   |
 |                 +---------+---------+                 |         |                   |                   |
 |                 | Authority Node B  |                 |         |                   |                   |
 |                 |   (Port 19202)    |                 |         |                   |                   |
 |                 +-------------------+                 |         |                   |                   |
 +---------------------------+---------------------------+         +-------------------+-------------------+
                             |                                                         |
                             +============== Physical Ethernet/USB Link ===============+
                                           (RTT Avg: 0.70 ms, Subnet: 192.168.55.0/24)
```

---

## 2. Asymmetric Node Failure & Reconnection

### Test 1: Remote Jetson Nano Process Termination (`SIGKILL`)
- Authority Node C was abruptly terminated with `SIGKILL` on the Jetson Nano.
- While Node C was dead, the Coordinator formed a quorum with surviving Host Nodes A and B.
- Transaction committed successfully: `COMMITTED` (Voters: `['A', 'B']`).
- Node C was restarted from its persistent flash WAL on `/dev/mmcblk0p1`.
- Node C reconnected over the physical network, requested catchup from Host Node A, and converged to an **identical bitwise `state_hash` and `evidence_root`**.

### Test 2: Cross-Machine Quorum During Host Node Failure
- Authority Node B was abruptly killed on the Host.
- Coordinator initiated a group commit with Host Node A and Remote Jetson Nano Node C.
- **Quorum of 2 succeeded across the physical Ethernet link**: `COMMITTED` (Voters: `['A', 'C']`).
- Demonstrates that the Jetson Nano operates as an independent, fully authoritative consensus peer over a real physical network.

---

## 3. Sustained Multi-Machine Performance

Workloads benchmarked across 30 timed repetitions per group size over the physical USB/RNDIS network link.

| Group Size | Latency p50 | Latency p90 | Latency p95 | Latency p99 | Throughput (Items/s) | Nano WAL Growth |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
|   1 | 188.25 ms | 217.33 ms | 221.06 ms | 241.93 ms | **5.31 items/s** | 5,149 B |
|   4 | 189.23 ms | 217.56 ms | 218.18 ms | 218.28 ms | **21.14 items/s** | 12,938 B |
|  16 | 218.86 ms | 235.44 ms | 247.14 ms | 248.35 ms | **73.11 items/s** | 33,019 B |
|  64 | 325.81 ms | 356.96 ms | 356.98 ms | 358.09 ms | **196.44 items/s** | 102,256 B |
| 256 | 684.42 ms | 719.17 ms | 721.58 ms | 744.76 ms | **374.04 items/s** | 368,349 B |

---

## 4. Architectural Findings & Key Takeaways

1. **Real Physical Inter-Device Consensus**: Consensus and group certificate formation operate reliably across distinct physical machines (Windows x86_64 host and Jetson Nano ARMv8).
2. **Network Resilience**: Physical transit delays (~0.7 ms RTT) are completely absorbed by the grouped protocol. At group size 256, multi-machine throughput matches single-device rates while distributing durable fault tolerance.
3. **Heterogeneous Cryptographic Verification**: Ed25519 signatures generated on ARMv8 silicon (Jetson Nano) verify identically against public keys on x86_64 silicon (Windows host), and vice versa.
4. **Flash Durability**: Authority Node C on the Nano persistently fsyncs WAL records to flash memory on every prepare and commit, surviving forced process kills without data loss.

---

## 5. Final Qualification Disposition

- **Two-Machine Physical Trial**: **`PASS`**
- **Disposition**: The UoW Q6 architecture is qualified across independent physical machines, proving genuine distributed consensus, fault tolerance, and non-volatile flash durability across network boundaries.

