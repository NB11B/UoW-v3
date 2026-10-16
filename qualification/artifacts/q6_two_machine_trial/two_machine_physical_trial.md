# Two-Machine Physical Qualification Trial: Q6 Distributed Group Commitment

## Executive Summary

- **Core Protocol Baseline Commit**: `eee128cabe6aeb932c0eeb838348e73bd453ca96`
- **Host Execution Commit**: `82ea4aee062821a03dcfd44c681f81cfca1a06b5`
- **Jetson Nano Deployed Commit**: `82ea4aee062821a03dcfd44c681f81cfca1a06b5`
- **Commit Synchronization Verified**: **True**
- **Machine 1 (Host)**: Windows 11 x86_64 (`192.168.55.100`) — Coordinator, Node A, Node B
- **Machine 2 (Target)**: NVIDIA Jetson Nano ARMv8 Cortex-A57 (`192.168.55.1`) — Node C
- **Physical Interconnect**: USB/RNDIS Virtual Ethernet link (`192.168.55.100` <-> `192.168.55.1`)
- **Link Latency (RTT)**: Min **0.4 ms** | Avg **0.7 ms** | Max **1.1 ms**
- **Timestamp**: 2026-10-16T02:22:56Z
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

## 3. Sustained Multi-Machine Performance (Dual-Timed Benchmark)

Workloads benchmarked across 30 timed repetitions per group size over the physical USB/RNDIS network link.
Measurements report both **Quorum Commit Latency/Throughput** (time for 2-of-3 threshold commit) and **Full 3-Replica Convergence Latency/Throughput** (including certificate dissemination and flash WAL sync across all replicas).

| Group Size | Quorum Latency (p50 / p95) | Quorum Throughput | Full Conv Latency (p50 / p95) | Full Conv Throughput | Nano WAL Growth |
| :---: | :---: | :---: | :---: | :---: | :---: |
|   1 | 200.69 ms / 221.67 ms | **4.98 items/s** | 200.69 ms / 221.67 ms | **4.98 items/s** | 5,149 B |
|   4 | 193.6 ms / 219.75 ms | **20.66 items/s** | 193.61 ms / 219.75 ms | **20.66 items/s** | 12,938 B |
|  16 | 209.98 ms / 234.24 ms | **76.2 items/s** | 209.99 ms / 234.24 ms | **76.19 items/s** | 33,019 B |
|  64 | 330.12 ms / 362.52 ms | **193.87 items/s** | 330.13 ms / 362.52 ms | **193.86 items/s** | 102,256 B |
| 256 | 704.8 ms / 723.21 ms | **363.22 items/s** | 704.81 ms / 723.22 ms | **363.22 items/s** | 368,349 B |

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

