from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "packaging" / "windows" / "build-portable.cmd"
PS1 = ROOT / "packaging" / "windows" / "build-portable.ps1"
DOC = ROOT / "docs" / "PORTABLE_BUILD.md"


def test_operator_launcher_bypasses_policy_only_for_child_process_and_logs_durably():
    text = CMD.read_text(encoding="utf-8")

    assert "-ExecutionPolicy Bypass" in text
    assert "logs\\verification" in text
    assert "issue-13-final-portable-build-%STAMP%.log" in text
    assert "Get-Content -LiteralPath $env:BUILD_LOG -Tail 30" in text
    assert "BUILD SUCCEEDED" in text
    assert "BUILD FAILED" in text


def test_operator_launcher_fails_closed_when_log_or_summary_evidence_is_missing():
    text = CMD.read_text(encoding="utf-8")

    assert "Unable to create log directory" in text
    assert "Unable to initialize log file" in text
    for marker in ("Source commit:", "Artifact:", "Bytes:", "SHA256:"):
        assert f'findstr /B /C:"{marker}" "%LOG%" >nul || goto :missing_summary' in text
    assert "exit /b 4" in text


def test_powershell_build_path_is_windows_powershell_51_compatible():
    text = PS1.read_text(encoding="utf-8")

    assert "[System.IO.Path]::GetRelativePath" not in text
    assert "Substring($artifactPrefix.Length)" in text
    assert "OrdinalIgnoreCase" in text
    assert "Inventory path escaped artifact directory" in text


def test_build_provenance_covers_artifact_defining_inputs_and_runtime_identity():
    text = PS1.read_text(encoding="utf-8")

    for path in (
        '"src"',
        '"pyproject.toml"',
        '"packaging/windows"',
        '"THIRD_PARTY_NOTICES.txt"',
        '"licenses"',
    ):
        assert path in text
    assert 'git diff --quiet $SourceCommit -- @sourceInputs' in text
    assert '3.12.10|64|AMD64' in text
    assert "Portable build requires CPython 3.12.10 x64" in text


def test_documentation_uses_supported_cmd_operator_path():
    text = DOC.read_text(encoding="utf-8")

    assert ".\\packaging\\windows\\build-portable.cmd" in text
    assert "supported operator entry point" in text
    assert "ExecutionPolicy Bypass" in text
    assert "Windows PowerShell 5.1" in text
