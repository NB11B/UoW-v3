# Jetson Nano Physical Qualification Trial: Q6 Persistent Distributed Commitment

## Executive Summary

- **Repository Baseline**: `NB11B/UoW-v3` at commit `eee128c`
- **Hardware Platform**: NVIDIA Jetson Nano | ARMv8 Cortex-A57 (4 cores @ 1.326 GHz) | 2GB LPDDR4
- **Operating System**: Linux 4.9.253-tegra (aarch64) | Python 3.11.17
- **Storage Device**: `/dev/mmcblk0p1` (eMMC / UHS-I MicroSD Flash)
- **Timestamp**: 2026-10-15T21:43:59Z
- **Physical Trial Verdict**: **`PASS`**

---

## 1. Physical Flash Persistence & fsync Latency

Disk persistence was directly exercised on the physical flash storage mount using non-volatile `os.fsync` calls across 100 sample writes.

| Metric | Flash fsync Latency (/dev/mmcblk0p1) |
| :--- | :---: |
| Minimum | **1.986 ms** |
| Median (p50) | **2.328 ms** |
| Mean | **2.526 ms** |
| 90th Percentile (p90) | **2.607 ms** |
| 95th Percentile (p95) | **2.775 ms** |
| Maximum | **16.087 ms** |

> [!NOTE]
> **Analytical vs Directly Measured Flash Synchronization**: The stated 256× reduction in flash disk synchronization operations is an analytical comparison against hypothetical per-item durable commits (which would require 2 fsyncs per item × 256 items = 512 fsyncs ≈ 1,218 ms on flash), whereas Q6 executes exactly 2 fsyncs per replica per group (one on PREPARE, one on COMMIT).

---

## 2. TCP Wire Serialization & Persistent WAL Growth

Network traffic was independently measured over loopback TCP sockets (`psutil.net_io_counters`), and persistent WAL sizes were measured directly from disk (`{node_id}.wal`) across the 3-node cluster.

| Group Size | Loopback TCP Bytes | Packets | Bytes / Member Item | Replica WAL Size (avg) | Total Cluster WAL Bytes |
| :---: | :---: | :---: | :---: | :---: | :---: |
|   1 | 18,255 B | 120 | **18255.0 B/item** | 5,149.0 B | 15,447 B |
|   4 | 21,288 B | 120 | **5322.0 B/item** | 12,938.0 B | 38,814 B |
|  16 | 33,420 B | 120 | **2088.8 B/item** | 33,019.0 B | 99,057 B |
|  64 | 81,960 B | 120 | **1280.6 B/item** | 102,256.0 B | 306,768 B |
| 256 | 276,904 B | 136 | **1081.7 B/item** | 368,349.0 B | 1,105,047 B |

> [!NOTE]
> As group size scales from 1 to 256, network serialization overhead drops from 18.2 KB per item to ~1.08 KB per item, while WAL logs on physical flash record full member evidence, group certificates, and cryptographic signatures.

---

## 3. Forced Process-Kill & Recovery Evaluation

- **Forced Termination Mechanism**: `SIGKILL (proc.kill)` (abrupt kernel kill without exception handling)
- **Termination Latency**: **57.89 ms**
- **Cold Process Spawn & WAL Replay**: **906.09 ms**
- **WAL Records Replayed**: 3
- **State Hash Exact Match**: `True`
- **Evidence Root Exact Match**: `True`
- **Post-Recovery Commit Resumption**: `True`
- **Recovery Verdict**: **`PASS`**

---

## 4. Sustained Performance on ARMv8 Cortex-A57

Workloads benchmarked across 30 timed repetitions per group size on physical ARMv8 silicon.

| Group Size | Latency p50 | Latency p90 | Latency p95 | Latency p99 | Throughput (Items/s) |
| :---: | :---: | :---: | :---: | :---: | :---: |
|   1 | 62.73 ms | 72.26 ms | 72.71 ms | 95.38 ms | **15.94 items/s** |
|   4 | 79.62 ms | 88.42 ms | 89.25 ms | 89.71 ms | **50.24 items/s** |
|  16 | 143.99 ms | 154.08 ms | 155.96 ms | 164.04 ms | **111.12 items/s** |
|  64 | 386.66 ms | 395.64 ms | 397.52 ms | 402.31 ms | **165.52 items/s** |
| 256 | 1374.62 ms | 1391.21 ms | 1397.77 ms | 1508.56 ms | **186.23 items/s** |

---

## 5. CPU and Memory Resource Utilization

| Group Size | Cluster Avg CPU | Peak Core CPU | Node Daemon RSS (avg) | Coord RSS | Total Cluster RSS |
| :---: | :---: | :---: | :---: | :---: | :---: |
|   1 | 17.53% | 100.0% | 32.8 MB | 38.0 MB | **136.47 MB** |
|   4 | 19.41% | 100.0% | 33.3 MB | 38.25 MB | **138.16 MB** |
|  16 | 21.63% | 100.0% | 34.5 MB | 38.79 MB | **142.25 MB** |
|  64 | 24.2% | 100.0% | 38.0 MB | 40.09 MB | **154.16 MB** |
| 256 | 24.82% | 100.0% | 50.7 MB | 44.49 MB | **196.66 MB** |

---

## 6. Full 12-Gate Acceptance Matrix Verification

All 12 gates (G01–G12) were independently evaluated and passed on the physical Jetson Nano hardware across all 5 group sizes [1, 4, 16, 64, 256].

| Gate | Description | Physical Hardware Verdict |
| :--- | :--- | :---: |
| **G01** | Baseline Equivalence | **PASS** (100% state & evidence equivalence) |
| **G02** | Group Certificate Validation | **PASS** (Ed25519 quorum & duplicate voter defense) |
| **G03** | Replay Protection | **PASS** (Stale pre-state & duplicate submission rejected) |
| **G04** | Tamper & Duplicate Voter Rejection | **PASS** (Strict distinct voter identity enforced) |
| **G05** | Insufficient Quorum | **PASS** (Coordinator aborts when quorum < 2) |
| **G06** | Conflicting Groups | **PASS** (No split-brain under concurrent proposals) |
| **G07** | Interrupted Preparation | **PASS** (Process kill during prepare rolls back cleanly) |
| **G08** | Interrupted Publication | **PASS** (Certificate-authenticated cooperative recovery) |
| **G09** | Replica Loss & Rejoin | **PASS** (Partitioned node catches up to tip via replay) |
| **G10** | Clock Skew & Scheduling Jitter | **PASS** (±24h skew & 50ms delay invariance verified) |
| **G11** | Restart Durability | **PASS** (Cold spawn and WAL replay maintains exact state) |
| **G12** | Performance Scaling | **PASS** (Grouped consensus amortizes flash & socket costs) |

---

## 7. Final Engineering Disposition

- **Jetson Nano Physical Trial**: **`PASS`**
- **Conclusion**: The host-side guarantees of Q6 (commit `eee128c`) hold under physical Jetson Nano flash storage (`/dev/mmcblk0p1`), 4-core ARMv8 CPU scheduling, TCP network sockets, and genuine OS process termination (`SIGKILL`).

