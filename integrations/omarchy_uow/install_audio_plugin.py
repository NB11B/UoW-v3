"""Stage the unpublished plugin in user-owned paths; refuse every conflict."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import subprocess


PLUGIN_ID = "nb11b.adaptive-audio"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(home: Path):
    return (home / ".config/omarchy/plugins" / PLUGIN_ID,
            home / ".local/share/omarchy-uow-audio",
            home / ".local/bin/omarchy-audio-worker",
            home / ".config/systemd/user/omarchy-uow-audio-gateway.service",
            home / ".local/state/omarchy-uow-audio")


def install(repo: Path, home: Path):
    repo, home = Path(repo).resolve(), Path(home).resolve()
    plugin, share, executable, unit, state = paths(home)
    created = [plugin, share, executable, unit, state / "tokens.json", state / "operator.token", state / "worker.token", state / "policy.json", state / "installed-files.json"]
    for path in created:
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
    plugin.parent.mkdir(parents=True, exist_ok=True)
    share.parent.mkdir(parents=True, exist_ok=True)
    executable.parent.mkdir(parents=True, exist_ok=True)
    unit.parent.mkdir(parents=True, exist_ok=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copytree(repo / "integrations/omarchy_uow/plugin", plugin)
    (share / "integrations/omarchy_uow").mkdir(parents=True)
    (share / "integrations/__init__.py").write_text("")
    for name in ("__init__.py", "service.py", "gateway.py", "audio_protocol.py", "audio_worker.py", "audio_runtime.py"):
        shutil.copy2(repo / "integrations/omarchy_uow" / name, share / "integrations/omarchy_uow" / name)
    shutil.copytree(repo / "src/uow", share / "uow", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    executable.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(share)!r})\nfrom integrations.omarchy_uow.audio_runtime import main\nraise SystemExit(main())\n")
    executable.chmod(0o755)
    operator = secrets.token_urlsafe(32)
    worker = secrets.token_urlsafe(32)
    token_map = {operator: "operator", worker: "audio_worker"}
    policy = {"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record", "audio.telemetry.ingest"]}
    for path, contents in ((state / "tokens.json", json.dumps(token_map)), (state / "operator.token", operator), (state / "worker.token", worker), (state / "policy.json", json.dumps(policy))):
        path.write_text(contents + "\n")
        path.chmod(0o600)
    gateway_socket = Path(f"/run/user/{os.getuid()}/omarchy-uow-audio/gateway.sock")
    unit.write_text("[Unit]\nDescription=Local UoW audio authority gateway\n\n[Service]\nType=simple\nEnvironment=PYTHONPATH=" + str(share) + "\nExecStart=" + sys.executable + " -m integrations.omarchy_uow.gateway --socket " + str(gateway_socket) + " --db " + str(state / "uow.db") + " --policy " + str(state / "policy.json") + " --tokens " + str(state / "tokens.json") + "\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n")
    files = [p for folder in (plugin, share) for p in folder.rglob("*") if p.is_file()]
    files.extend((executable, unit))
    inventory = state / "installed-files.json"
    inventory.write_text(json.dumps({str(p): sha(p) for p in files}, sort_keys=True) + "\n")
    inventory.chmod(0o600)
    return {"plugin": str(plugin), "gateway": str(unit), "worker": str(executable), "state": str(state)}


def uninstall(home: Path, stop):
    home = Path(home).resolve()
    plugin, share, executable, unit, state = paths(home)
    inventory = state / "installed-files.json"
    expected = json.loads(inventory.read_text())
    if not isinstance(expected, dict):
        raise ValueError("INSTALL_INVENTORY")
    allowed = {str(executable), str(unit)}
    for name, digest in expected.items():
        path = Path(name)
        if (not isinstance(digest, str) or not (path.is_relative_to(plugin) or path.is_relative_to(share) or name in allowed)
                or not path.is_file() or path.is_symlink() or sha(path) != digest):
            raise ValueError("INSTALLED_FILE_CHANGED: " + name)
    actual = {str(p) for folder in (plugin, share) for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual != {name for name in expected if Path(name).is_relative_to(plugin) or Path(name).is_relative_to(share)}:
        raise ValueError("INSTALLED_FILES_CHANGED")
    stop()
    shutil.rmtree(plugin)
    shutil.rmtree(share)
    executable.unlink()
    unit.unlink()
    inventory.unlink()
    return {"retained_receipts": str(state / "uow.db")}


def stop_runtime():
    subprocess.run(["omarchy", "plugin", "disable", PLUGIN_ID], check=True)
    subprocess.run(["systemctl", "--user", "disable", "--now", "omarchy-uow-audio-gateway.service"], check=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    print(json.dumps(uninstall(args.home, stop_runtime) if args.uninstall else install(args.repo, args.home), indent=2))


if __name__ == "__main__":
    main()
