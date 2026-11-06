"""Install the built Adaptive Audio window into user-owned paths only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import uuid


def install(project: Path, home: Path) -> dict:
    project, home = Path(project).resolve(), Path(home).resolve()
    mapping = {
        home / ".local/bin/adaptive-audio": project / "build/app/adaptive-audio",
        home / ".local/share/applications/adaptive-audio.desktop": project / "desktop/adaptive-audio.desktop",
        home / ".local/share/icons/hicolor/scalable/apps/adaptive-audio.svg": project / "desktop/adaptive-audio.svg",
    }
    for destination, source in mapping.items():
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        if not source.is_file():
            raise FileNotFoundError(source)
    created = []
    try:
        for destination, source in mapping.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + ".install-" + uuid.uuid4().hex)
            try:
                shutil.copy2(source, temp)
                temp.chmod(0o755 if destination.name == "adaptive-audio" else 0o644)
                os.replace(temp, destination)
                created.append(destination)
            finally:
                temp.unlink(missing_ok=True)
    except Exception:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    return {"binary": str(home / ".local/bin/adaptive-audio"),
            "desktop": str(home / ".local/share/applications/adaptive-audio.desktop"),
            "icon": str(home / ".local/share/icons/hicolor/scalable/apps/adaptive-audio.svg")}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).resolve().parent, args.home), indent=2))
