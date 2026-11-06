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
import uuid


PLUGIN_ID = "nb11b.adaptive-audio"
LEGACY_POLICY = {"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record", "audio.telemetry.ingest"]}
CURRENT_POLICY = {"operator": ["audio.stream.start", "audio.stream.stop", "audio.dsp.crossover.set"], "audio_worker": ["audio.effect.record", "audio.telemetry.ingest", "audio.dsp.crossover.effect"]}


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
    policy = CURRENT_POLICY
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


def upgrade_sources(repo: Path, home: Path) -> dict[Path, Path]:
    plugin, share, _, _, _ = paths(home)
    source_plugin = repo / "integrations/omarchy_uow/plugin"
    mapping = {plugin / p.relative_to(source_plugin): p for p in source_plugin.rglob("*") if p.is_file()}
    source_code = repo / "integrations/omarchy_uow"
    for name in ("__init__.py", "service.py", "gateway.py", "audio_protocol.py", "audio_worker.py", "audio_runtime.py"):
        mapping[share / "integrations/omarchy_uow" / name] = source_code / name
    return mapping


def upgrade_preflight(repo: Path, home: Path) -> dict:
    repo, home = Path(repo).resolve(), Path(home).resolve()
    plugin, share, executable, unit, state = paths(home)
    inventory_path = state / "installed-files.json"
    inventory = json.loads(inventory_path.read_text())
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("INSTALL_INVENTORY")
    allowed = {str(executable), str(unit)}
    for name, digest in inventory.items():
        path = Path(name)
        if (not isinstance(digest, str) or not (path.is_relative_to(plugin) or path.is_relative_to(share) or name in allowed)
                or not path.is_file() or path.is_symlink() or sha(path) != digest):
            raise ValueError("INSTALLED_FILE_CHANGED: " + name)
    mapping = upgrade_sources(repo, home)
    for destination, source in mapping.items():
        if str(destination) not in inventory or not source.is_file() or destination.is_symlink():
            raise ValueError("UPGRADE_SOURCE_CONFLICT: " + str(destination))
    policy_path = state / "policy.json"
    policy = json.loads(policy_path.read_text())
    if policy not in (LEGACY_POLICY, CURRENT_POLICY) or policy_path.is_symlink():
        raise ValueError("POLICY_CHANGED")
    return {"mapping": mapping, "inventory": inventory, "policy": policy, "policy_path": policy_path, "inventory_path": inventory_path}


def upgrade(repo: Path, home: Path, replace=None) -> dict:
    repo, home = Path(repo).resolve(), Path(home).resolve()
    preflight = upgrade_preflight(repo, home)
    _, _, _, _, state = paths(home)
    backup = state / ("upgrade-backup-" + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    mapping = preflight["mapping"]
    destinations = [*mapping, preflight["policy_path"], preflight["inventory_path"]]
    for index, destination in enumerate(destinations):
        shutil.copy2(destination, backup / str(index))
    (backup / "paths.json").write_text(json.dumps([str(path) for path in destinations]) + "\n")
    (backup / "paths.json").chmod(0o600)
    inventory = dict(preflight["inventory"])
    modified = []
    replace = replace or os.replace
    try:
        for destination, source in mapping.items():
            temp = destination.with_name(destination.name + ".upgrade-" + uuid.uuid4().hex)
            try:
                shutil.copy2(source, temp)
                replace(temp, destination)
                modified.append(destination)
            finally:
                temp.unlink(missing_ok=True)
            inventory[str(destination)] = sha(destination)
        for destination, data in ((preflight["policy_path"], json.dumps(CURRENT_POLICY) + "\n"),
                                  (preflight["inventory_path"], json.dumps(inventory, sort_keys=True) + "\n")):
            temp = destination.with_name(destination.name + ".upgrade-" + uuid.uuid4().hex)
            try:
                temp.write_text(data)
                temp.chmod(destination.stat().st_mode & 0o777)
                replace(temp, destination)
                modified.append(destination)
            finally:
                temp.unlink(missing_ok=True)
    except Exception:
        for destination in reversed(modified):
            index = destinations.index(destination)
            shutil.copy2(backup / str(index), destination)
        shutil.rmtree(backup)
        raise
    return {"backup": str(backup), "updated_files": len(mapping), "preserved_state": str(state)}


def rollback_upgrade(backup: Path, home: Path, repo: Path | None = None) -> dict:
    home = Path(home).resolve()
    repo = Path(repo).resolve() if repo is not None else Path(__file__).resolve().parents[2]
    plugin, share, _, _, state = paths(home)
    backup = Path(backup).resolve()
    if backup.parent != state or not backup.name.startswith("upgrade-backup-") or not backup.is_dir():
        raise ValueError("UPGRADE_BACKUP_PATH")
    current = upgrade_preflight(repo, home)
    destinations = [Path(name) for name in json.loads((backup / "paths.json").read_text())]
    expected = [*current["mapping"], current["policy_path"], current["inventory_path"]]
    if destinations != expected or any(not (backup / str(i)).is_file() or (backup / str(i)).is_symlink() for i in range(len(destinations))):
        raise ValueError("UPGRADE_BACKUP_CONTENTS")
    stage = state / ("rollback-stage-" + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    for index, destination in enumerate(destinations):
        shutil.copy2(destination, stage / str(index))
    modified = []
    try:
        for index, destination in enumerate(destinations):
            temp = destination.with_name(destination.name + ".rollback-" + uuid.uuid4().hex)
            try:
                shutil.copy2(backup / str(index), temp)
                os.replace(temp, destination)
                modified.append(index)
            finally:
                temp.unlink(missing_ok=True)
    except Exception:
        for index in reversed(modified):
            shutil.copy2(stage / str(index), destinations[index])
        raise
    finally:
        shutil.rmtree(stage)
    return {"restored_files": len(destinations), "backup": str(backup)}


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
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--check-upgrade", action="store_true")
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    if sum((args.uninstall, args.upgrade, args.check_upgrade, args.rollback is not None)) > 1:
        parser.error("choose one action")
    if args.uninstall:
        result = uninstall(args.home, stop_runtime)
    elif args.upgrade:
        result = upgrade(args.repo, args.home)
    elif args.check_upgrade:
        checked = upgrade_preflight(args.repo, args.home)
        result = {"status": "ready", "files": len(checked["mapping"]), "policy": "current" if checked["policy"] == CURRENT_POLICY else "legacy"}
    elif args.rollback is not None:
        result = rollback_upgrade(args.rollback, args.home, args.repo)
    else:
        result = install(args.repo, args.home)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
