# C++ Conformance Bridge

This module provides the semantic bridge between Python test runners and the host-native **C++ Unit-of-Work Runtime**.

---

## 1. Architectural Role

The bridge acts strictly as an execution harness:
- It discovers and feeds canonical test vector files to `conformance_runner.exe`.
- It captures the standard output stream emitted by native C++ and parses the resulting execution envelope.
- It **does not** compute mutations, evaluate guards, determine authority, resolve idempotency, or calculate evidence. All semantic operations belong exclusively to the compiled C++ kernel.

---

## 2. Compilation & Usage

The native runner is compiled using standard C++17:

```powershell
C:\Strawberry\c\bin\g++.exe `
  -std=c++17 `
  -I runtimes/cpp/include `
  runtimes/cpp/native_state.cpp `
  runtimes/cpp/native_evidence.cpp `
  runtimes/cpp/native_idempotency.cpp `
  runtimes/cpp/native_protocol.cpp `
  runtimes/cpp/conformance_runner.cpp `
  -o runtimes/cpp/conformance_runner.exe
```

Run all 16 vectors:

```powershell
.\runtimes\cpp\conformance_runner.exe --all conformance/vectors
```
