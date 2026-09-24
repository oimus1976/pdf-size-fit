from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_portable_build_tracks_and_copies_application_license() -> None:
    script = (ROOT / "packaging" / "windows" / "build-portable.ps1").read_text(
        encoding="utf-8"
    )

    assert '"LICENSE",' in script
    assert (
        'Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") '
        "-Destination $artifactDir"
    ) in script


def test_portable_notice_matches_current_application_license() -> None:
    notice = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")

    assert "licensed under the MIT License" in notice
    assert "RUNTIME_INVENTORY.txt" in notice
    assert "1242df81e2a3bc6b0b00ddd9ef19595cb3fb548a" not in notice
    assert "no selected open-source license" not in notice
