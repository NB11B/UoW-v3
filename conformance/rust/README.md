# Rust Native Conformance Runner & Bridge

This directory contains the bridge harness for evaluating the native Rust runtime (`uow-runtime`) against the canonical Unit-of-Work (UoW) v3 test vectors located in `conformance/vectors/`.

## Architecture

- **Independent Runtime**: Built in `runtimes/rust/` as a standalone crate (`uow-runtime`).
- **Binary Runner**: `runtimes/rust/src/bin/conformance_runner.rs` compiles to `conformance_runner.exe`.
- **Python Bridge**: `conformance/rust/vector_bridge.py` facilitates invoking the executable and capturing JSON outputs for verification in pytest suites.
- **Coverage**: Executes and verifies all 16 canonical golden vectors ($V_{16}$), guaranteeing:
  $$\forall v \in V_{16}, \quad \text{Exec}_{\text{Rust}}(v) = \text{Expected}(v)$$

## CLI Execution

Run batch verification directly from the shell:

```powershell
cargo run --release --bin conformance_runner --manifest-path runtimes/rust/Cargo.toml -- --all conformance/vectors
```

Run an individual vector:

```powershell
cargo run --release --bin conformance_runner --manifest-path runtimes/rust/Cargo.toml -- conformance/vectors/001_execute_one_success.json
```
