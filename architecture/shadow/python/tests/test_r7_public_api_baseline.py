from pathlib import Path
import hashlib
import re


REPO = Path(__file__).resolve().parents[4]
APPROVED_POST_A3_TOPLEVEL_BLOB = "766ce31ecd63e30376fa8771f84c4a104ed31247"
POLICY_ORACLE_COMMIT = "aa886329298f87e8b006501d47dd89eb8f0d4a3b"


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("utf-8") + data
    return hashlib.sha1(payload).hexdigest()


def test_r7_public_api_surface_preserves_baseline_except_approved_post_a3_namespace():
    text = (REPO / "architecture" / "PUBLIC_API_BASELINE.yaml").read_text(encoding="utf-8")
    pairs = re.findall(
        r"^  (pyproject\.toml|src/uow(?:/[^:]+)?/__init__\.py): ([0-9a-f]{40})$",
        text,
        flags=re.MULTILINE,
    )

    assert len(pairs) == 8
    for rel, expected in pairs:
        observed = _git_blob_sha1(REPO / rel)
        if rel == "src/uow/__init__.py":
            assert observed == APPROVED_POST_A3_TOPLEVEL_BLOB
            assert observed != expected
            continue
        assert observed == expected, rel

    migration = (REPO / "architecture" / "post_a3_policy_api_merge.yaml").read_text(encoding="utf-8")
    assert f"source_commit: {POLICY_ORACLE_COMMIT}" in migration
    assert "target_namespace: uow.policy" in migration
    assert "historical_baseline_preserved: true" in migration
    assert "top_level_delta: namespace_export_only" in migration


def test_r7_facade_remains_outside_installed_uow_package():
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.packages.find]" in pyproject
    assert 'where = ["src"]' in pyproject
    assert "implementations/python" not in pyproject

    import uow
    assert "/src/uow/" in str(Path(uow.__file__).as_posix())
