import http.client
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fetch_module():
    spec = importlib.util.spec_from_file_location("fetch_corpus", ROOT / "scripts" / "fetch_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fetch_corpus_survives_incomplete_read(tmp_path, monkeypatch, capsys):
    mod = _fetch_module()
    manifest = tmp_path / "m.json"
    manifest.write_text('[{"file": "a.prism", "sha256": "0", "download_url": "https://example.invalid/a"}]')
    monkeypatch.setattr(mod, "MANIFEST", manifest)

    def boom(*a, **k):
        raise http.client.IncompleteRead(b"abc", 10)

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert mod.main(["--dest", str(tmp_path / "c")]) == 1
    assert "FAILED   a.prism" in capsys.readouterr().err
    assert not list((tmp_path / "c").glob("*.part"))


def test_fetch_corpus_removes_part_file_on_truncated_body(tmp_path, monkeypatch):
    mod = _fetch_module()
    manifest = tmp_path / "m.json"
    manifest.write_text('[{"file": "a.prism", "sha256": "0", "download_url": "https://example.invalid/a"}]')
    monkeypatch.setattr(mod, "MANIFEST", manifest)

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            raise http.client.IncompleteRead(b"abc", 10)

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert mod.main(["--dest", str(tmp_path / "c")]) == 1
    assert not list((tmp_path / "c").glob("*.part"))


def test_manifest_in_ships_test_helpers():
    text = (ROOT / "MANIFEST.in").read_text()
    for line in ("graft tests", "graft docs", "include scripts/fetch_corpus.py"):
        assert line in text.splitlines()


def test_manifest_in_ships_project_files():
    lines = (ROOT / "MANIFEST.in").read_text().splitlines()
    for name in ("CHANGELOG.md", "CITATION.cff", "SECURITY.md"):
        assert f"include {name}" in lines


def test_typed_marker_and_single_version_source():
    assert (ROOT / "src" / "prsmfile" / "py.typed").is_file()
    py = (ROOT / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in py
    assert "\nversion = " not in py.split("[tool.setuptools.dynamic]")[0]
