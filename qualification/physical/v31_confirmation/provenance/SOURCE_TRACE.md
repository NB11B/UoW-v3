# Source Trace & Provenance: Milestone v3.1-M5 Physical Reconfirmation

## 1. Lineage & Hardware Mapping

- **Campaign**: `V31-PHYS-CONFIRM`
- **Milestone**: `v3.1-M5`
- **Base Commit**: `2132f0a7cb078d882829a10aa116a9f89542b79c`
- **Branch**: `v3.1/physical-reconfirmation`
- **Prerequisites**:
  - `v3.1-m1-kryonos-qualified`
  - `v3.1-m2-atomic-economics-qualified`
  - `v3.1-m3-cpp-16vec-qualified`
  - `v3.1-m4-rust-runtime-qualified`

## 2. Hardware Topology

| Node Identifier | Board Environment | MCU / Architecture | Role | Physical Port |
|---|---|---|---|---|
| `auth_a_esp32` | ESP32-S3-DevKitC-1-N16R8 | Xtensa Dual-Core LX7 @ 240MHz | Authority A (KryonOS + Native Gate) | `COM4` |
| `auth_b_uno_q` | Arduino UNO Q | Arm Cortex-M33 (STM32U585) @ 160MHz | Authority B (STM32 Authority) | `COM3` |
| `auth_c_laptop` | Laptop Host x86-64 | AMD64 / Windows 11 | Authority C (Local Authority Service) | `localhost:8080` |
| `witness_rust` | Laptop Host x86-64 | AMD64 / Rust 1.98.1 | Host Realization Witness (`uow-runtime`) | In-process / CLI |

---

## 3. Cryptographic Hashes (SHA-256)

### 3.1 Firmware Sources
| File | SHA-256 Digest |
|---|---|
| `runtimes/embedded/esp32/main.cpp` | `06b9c7c92c0a1e6d528b7ffc42b39344276d124298a4fabf711a7a3102cd2b05` |
| `runtimes/embedded/esp32/uow_embedded.cpp` | `65e89f9e126d298181263d42a3f0557067466e68fe7cadccd04e51d580cc644b` |
| `runtimes/embedded/esp32/uow_embedded.hpp` | `458c376c39f89ab20e545e5c2f2092c27ad4e5274924218692da767fbe3e9b5a` |
| `runtimes/embedded/arduino/uno_q_authority.ino` | `fa310769ecc057541407f54984d53b921c114f7c609e4795ce711bfbe8abe24f` |
| `runtimes/embedded/arduino/uow_embedded.cpp` | `3b785dc36d54575447b7414ed14b38d72726eef2b29e07aa72e82cca47dc1abe` |
| `runtimes/embedded/arduino/uow_embedded.hpp` | `458c376c39f89ab20e545e5c2f2092c27ad4e5274924218692da767fbe3e9b5a` |

### 3.2 Qualification Vectors
| Vector | SHA-256 Digest |
|---|---|
| `qualification/physical/v31_confirmation/vectors/pairwise_agreement.json` | `41c69728b291ff062a8031a787e9ad995f550e6df2198bd16da257d77ac4371c` |
| `qualification/physical/v31_confirmation/vectors/quorum_pairs.json` | `05a976d72d6d846e3b6c734240c9c122509085a2cc91696c35c2abbfda535685` |
| `qualification/physical/v31_confirmation/vectors/partition_fail_closed.json` | `2744dd045409ac37762bf47c6df8a1495d1bf0611974ae3c1b8e4e905effd59d` |
| `qualification/physical/v31_confirmation/vectors/stale_replay.json` | `3eb11fac0c85a0b8c9f674daff77c7f54777710a3ee46525af93feaf0c4887c9` |
| `qualification/physical/v31_confirmation/vectors/realization_parity.json` | `f074eee663ffd6735a9d4ac3651fd7ee9a97b7d45ea0a25f654d0f095adbc873` |
| `qualification/physical/v31_confirmation/vectors/recovery_continuity.json` | `0fa7e6cac6d04b69ac1640d35e45a3d7bb9c10f471ed71dcc36a5034e703a107` |

---

## 4. Compiler Toolchain Attestation

- **PlatformIO Core**: `6.1.19` (Framework: `espressif32`, ESP-IDF 5.x)
- **Arduino CLI**: `1.1.2` (Core: `arduino:zephyr_stm32`, toolchain: `arm-none-eabi-gcc 12.3.1`)
- **Host C++**: `g++.exe 13.2.0 (MinGW-W64)`
- **Rust Toolchain**: `rustc 1.98.1 (48a229cea 2026-09-01)`
- **Python**: `Python 3.13.11 (tags/v3.13.11:7d92170)`
