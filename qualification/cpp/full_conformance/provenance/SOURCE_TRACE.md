# Source Trace & Immutable Provenance: C++ 16/16 Conformance (v3.1-M3)

This document establishes the exact cryptographic digests, baseline executables, and compiler specifications for **Milestone v3.1-M3: Native C++ 16/16 Conformance**.

---

## 1. Toolchain & Host Environment

- **Compiler**: `g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r8) 13.2.0`
- **Compiler Path**: `C:\Strawberry\c\bin\g++.exe`
- **Language Standard**: `C++17` (`-std=c++17 -I runtimes/cpp/include`)
- **Compilation Host**: Windows x86_64

---

## 2. Frozen Baseline (Prior to M3 Development)

Before modifying the C++ layer, the existing embedded core semantics runner was frozen and compiled to establish baseline behavior:

| Artifact | Path | SHA-256 Digest |
|---|---|---|
| **Core Semantics Source** | `runtimes/cpp/core_semantics.cpp` | `7e1897f8e955636b708c554fc6061f10515a897f853bd506b43273538ddf5d0e` |
| **Embedded Core Source** | `runtimes/embedded/esp32/uow_embedded.cpp` | `38ba8f6d15f1225a1810d80de950216ccc03096cc828cbd4eb47409edb10c250` |
| **Baseline Executable** | `qualification/cpp/full_conformance/baseline/core_semantics.exe` | `86e9f933c728c09486c921a3ac2db616364186009d82b644ba51e3261fdee28e` |

Baseline verification tests executed successfully:
- `core_semantics.exe transfer`: `{"r0":0,"r1":8,"pc":2,"sequence":12,"halted":true,"evidence_steps":12,"evidence_valid":true}`
- `core_semantics.exe tamper_state`: `{"committed":false,"reason":"STATE_DIVERGENCE",...}`
- `core_semantics.exe tamper_prehash`: `{"committed":false,"reason":"STALE_PRE_STATE",...}`
- `core_semantics.exe tamper_route`: `{"committed":false,"reason":"ROUTE_DIVERGENCE",...}`

---

## 3. Host-Native C++ Conformance Implementation Artifacts

| Component | Path | SHA-256 Digest |
|---|---|---|
| **Native Types Header** | `runtimes/cpp/include/uow_native_types.hpp` | `15d883eb3b8028369109107d013d72fa3c7ced61e1f7e921a45d9a516865ba6a` |
| **Native State Header** | `runtimes/cpp/include/uow_native_state.hpp` | `6a052c8cc223968b497d563a014bc49ca7b079ff75a08d1f0e60a8f4a6d1bf59` |
| **Native Evidence Header** | `runtimes/cpp/include/uow_native_evidence.hpp` | `584d84b8e2205431931c41d7bae975d6391b4cd63e07a70d9c96c765e0a05b9a` |
| **Native Idempotency Header** | `runtimes/cpp/include/uow_native_idempotency.hpp` | `5ebba1c20b716da02e079ec9016a8b75cf8fd699c46dac997918743549b917f2` |
| **Native Protocol Header** | `runtimes/cpp/include/uow_native_protocol.hpp` | `d9bdf30001d25c9b33b2a2e3523b65dab4912015c2802e262540e8f15f97837d` |
| **State Implementation** | `runtimes/cpp/native_state.cpp` | `c5b58f5fe21baee1972bbe1061caf575c585857bf9e3448301490d52ac20f922` |
| **Evidence Implementation** | `runtimes/cpp/native_evidence.cpp` | `6d0292da702380d7bcfd3fa92232d238dcc9f95fb5218305727b81a9327e3538` |
| **Idempotency Implementation** | `runtimes/cpp/native_idempotency.cpp` | `10d02bb8eeff8b6978f6286ceb0a383160a3b9bc2ed318646de5b46533ab61ef` |
| **Protocol Implementation** | `runtimes/cpp/native_protocol.cpp` | `fa028252bdeaa36f48fffd6e0f18484fd91f7e168e2a6ce89e0671a81db244b1` |
| **Conformance Runner** | `runtimes/cpp/conformance_runner.cpp` | `d15359dfce6e166028c0a7a593e16ac459eeabb590db4746827d59cfc97df1b6` |
| **Compiled Runner Binary** | `runtimes/cpp/conformance_runner.exe` | `765b32610472a0c0f75e438ea15da70b33f005db14a883238ac40c7c7e3ead34` |
| **Python Conformance Bridge** | `conformance/cpp/vector_bridge.py` | `feda56064ff76b94c4b6b41c2237492d129330be6f083a03fa8b7c5a845a3510` |
| **Automated Test Suite** | `tests/test_cpp_full_conformance.py` | `96095a308121eec6bea9200efc6fdd8af82436bd30bb951cfd561ce96186c9d3` |

---

## 4. Immutable Canonical Vector Trace

All 16 canonical golden test vectors in `conformance/vectors/` were preserved without modification:

| Vector File | Canonical SHA-256 Digest | Status |
|---|---|---|
| `001_execute_one_success.json` | `f8d3bfcc8d7c0fd077be0c864aef9b58680bd715717302d963c760250a3e9215` | PASSED |
| `002_guard_unsatisfied_rejection.json` | `ad0f436993d838f71cb8006f73806586cc9595c5ecbda5014c9c2ea2e8cccc99` | PASSED |
| `003_stale_pre_state_rejection.json` | `913b0b373b6110fbeda8848fd6799de215072b533de617ccd4dea62f737ae1ab` | PASSED |
| `004_tampered_proposal_rejection.json` | `5e5d1464ccbe9422b17970f23f7abf7ba36cd3a6930e1c8acbb0e6814665c406` | PASSED |
| `005_evidence_chain_continuity.json` | `72053c1382e6763f61deb6e355c227d707745bd7975679523e900b19289af91a` | PASSED |
| `006_authority_unauthorized_rejection.json` | `7f93305051fe716f11f7b791b0d1e5ce352f59e03cf427f22bd04d9d80a2ce61` | PASSED |
| `007_idempotency_replay.json` | `723d183119b40811f6221253c9a7e06ff9bdfa7c1780db57d238b6e9b3e9bd11` | PASSED |
| `008_domain_inventory_reserve.json` | `370dbb0ba8b9910edefa91ee03b30dcee0488fd05553c130bfc239f1541d7c0d` | PASSED |
| `009_malformed_envelope_rejection.json` | `2c53a20bf612a08e5d95214ffd5d940e7df7d9a291010c27a94968ca50891421` | PASSED |
| `010_unknown_protocol_version.json` | `d3a22e0fc418d8256e32f39ac9ccd99b94d85a44a086c0a0db4062ffce7a0be5` | PASSED |
| `011_idempotency_payload_conflict.json` | `1e075351de1f4fd15d20d329e02e0655403795418d126b6cc7a67c33ddf75dc4` | PASSED |
| `012_authority_escalation_attempt.json` | `37282c156124daf53d9a5cae0cc6834d5f872ffc23162fbf87281bfc4009cb17` | PASSED |
| `013_evidence_tampering_rejection.json` | `f18e7202b9d6d44c8c3051d631bf7b52455a1b69f8e1fe3646055522ca276000` | PASSED |
| `014_unicode_and_special_characters.json` | `ca894bd657c6ca51220430840dde937fbb2d08255d6882b757b270b0c70157bf` | PASSED |
| `015_integer_boundary_cases.json` | `cdd2146ecc12ae2de046f706c9d5999b067722fef71280b19c561f53aa3d6890` | PASSED |
| `016_transport_retry_duplicate_ack.json` | `313f921b80978437b0c2c47e078a57b283af43e9e963498ab5b6251d73082161` | PASSED |
