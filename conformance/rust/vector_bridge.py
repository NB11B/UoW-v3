"""Native Rust conformance bridge. Execute only the independently compiled Rust runner."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

RUST_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtimes" / "rust"

class RustVectorBridge:
    def __init__(self, runner_exe: Path | str | None = None) -> None:
        name = "conformance_runner.exe" if os.name == "nt" else "conformance_runner"
        candidates = [RUST_RUNTIME_DIR / "target" / mode / name for mode in ("release", "debug")]
        if runner_exe is not None:
            self.runner_exe = Path(runner_exe)
            if not self.runner_exe.is_file():
                raise FileNotFoundError(self.runner_exe)
        else:
            if not any(p.is_file() for p in candidates):
                self._compile_runner()
            self.runner_exe = next((p for p in candidates if p.is_file()), None)
            if self.runner_exe is None:
                raise FileNotFoundError("Cargo succeeded but native conformance runner is missing")

    def _compile_runner(self) -> None:
        subprocess.run(["cargo", "build", "--release"], cwd=RUST_RUNTIME_DIR,
                       capture_output=True, text=True, check=True)

    def execute_vector(self, vector_file: Path | str) -> Dict[str, Any]:
        proc = subprocess.run([str(self.runner_exe), str(vector_file)],
                              capture_output=True, text=True, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"Rust runner exited {proc.returncode}: {proc.stderr}")
        return json.loads(proc.stdout)

    def execute_all(self, vectors_dir: Path | str) -> Tuple[int, int, str]:
        proc = subprocess.run([str(self.runner_exe), "--all", str(vectors_dir)],
                              capture_output=True, text=True, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"Rust batch runner exited {proc.returncode}: {proc.stderr}")
        output = proc.stdout.strip()
        lines = output.splitlines()
        passed = sum("PASS" in line for line in lines)
        failed = sum("FAIL" in line or "ERROR" in line for line in lines)
        return passed, passed + failed, output
