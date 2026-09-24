from pathlib import Path
import hashlib
import re


REPO = Path(__file__).resolve().parents[4]


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("utf-8") + data
    return hashlib.sha1(payload).hexdigest()


def test_r7_public_api_surface_matches_frozen_main_baseline():
    text = (REPO / "architecture" / "PUBLIC_API_BASELINE.yaml").read_text(encoding="utf-8")
    pairs = re.findall(
        r"^  (pyproject\.toml|src/uow(?:/[^:]+)?/__init__\.py): ([0-9a-f]{40})$",
        text,
        flags=re.MULTILINE,
    )

    assert len(pairs) == 8
    for rel, expected in pairs:
        assert _git_blob_sha1(REPO / rel) == expected, rel


def test_r7_facade_remains_outside_installed_uow_package():
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.packages.find]" in pyproject
    assert 'where = ["src"]' in pyproject
    assert "implementations/python" not in pyproject

    import uow
    assert "/src/uow/" in str(Path(uow.__file__).as_posix())
