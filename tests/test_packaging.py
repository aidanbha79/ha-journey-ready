import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_archive_contains_runtime_only(tmp_path):
    target = tmp_path / "journey_ready.zip"
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_release.py"), str(target)],
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "brand/icon.png" in names
        assert not any(
            "__pycache__" in name or ".pyc" in name or name.startswith("tests/") for name in names
        )
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["domain"] == "journey_ready"
        assert archive.read("brand/icon.png").startswith(b"\x89PNG\r\n\x1a\n")


def test_metadata_and_translations_parse():
    component = ROOT / "custom_components/journey_ready"
    manifest = json.loads((component / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["filename"] == "journey_ready.zip"
    assert manifest["config_flow"] is True
    assert manifest["documentation"] == "https://github.com/aidanbha79/ha-journey-ready"
    assert json.loads((component / "translations/en.json").read_text())["options"]["step"]["alexa"][
        "data"
    ]["alexa_question_script"]
