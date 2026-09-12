"""Shell command classification tests (spec §26, §39)."""

from __future__ import annotations

import pytest

from greatsage.tools.shell_classifier import CommandClass, classify_command


@pytest.mark.parametrize(
    "command",
    [
        ["where", "python"],
        ["python", "--version"],
        ["python", "-V"],
        ["python", "--help"],
        ["git", "status"],
        ["git", "log", "--oneline"],
        ["git", "diff"],
        ["git", "branch", "-a"],
        ["git", "rev-parse", "HEAD"],
        ["dir"],
        ["ipconfig"],
        ["ping", "localhost"],
        ["hostname"],
        ["whoami"],
        ["systeminfo"],
        ["tasklist"],
        ["tree"],
        ["python.exe", "--version"],
        ["python"],
        ["C:\\Windows\\System32\\where.exe", "python"],
    ],
)
def test_safe_commands(command: list[str]) -> None:
    assert classify_command(command) is CommandClass.SAFE


@pytest.mark.parametrize(
    "command",
    [
        ["python", "-c", "print(1)"],
        ["python", "script.py"],
        ["git", "checkout", "main"],
        ["git", "pull"],
        ["git", "commit", "-m", "x"],
        ["git", "push"],
        ["pip", "install", "numpy"],
        ["npm", "install"],
        ["curl", "https://example.com"],
        ["mkdir", "build"],
        ["move", "a", "b"],
        ["rename", "a", "b"],
        ["copy", "a", "b"],
        ["tar", "-xzf", "x.tar.gz"],
        ["some-unknown-tool"],
        ["git"],
    ],
)
def test_restricted_commands(command: list[str]) -> None:
    assert classify_command(command) is CommandClass.RESTRICTED


@pytest.mark.parametrize(
    "command",
    [
        ["del", "file.txt"],
        ["rm", "-rf", "/"],
        ["rmdir", "x"],
        ["erase", "file.txt"],
        ["taskkill", "/F", "/IM", "app.exe"],
        ["shutdown", "/s"],
        ["reg", "delete", "HKCU"],
        ["net", "user"],
        ["sc", "stop", "svc"],
        ["wmic", "process", "delete"],
        ["cmd", "/c", "del", "x"],
        ["powershell", "-Command", "x"],
        ["start", "notepad"],
        ["wsl", "ls"],
    ],
)
def test_dangerous_commands(command: list[str]) -> None:
    assert classify_command(command) is CommandClass.DANGEROUS


@pytest.mark.parametrize(
    "command",
    [
        ["format", "C:"],
        ["fdisk"],
        ["diskpart"],
        ["chkdsk", "C:"],
        ["sfc", "/scannow"],
        ["dism", "/online"],
        ["regedit"],
        ["gpedit"],
        ["manage-bde"],
        ["vssadmin"],
    ],
)
def test_forbidden_commands(command: list[str]) -> None:
    assert classify_command(command) is CommandClass.FORBIDDEN


def test_empty_command_forbidden() -> None:
    assert classify_command([]) is CommandClass.FORBIDDEN


def test_git_destructive_classified_dangerous() -> None:
    assert classify_command(["git", "reset", "--hard"]) is CommandClass.DANGEROUS
    assert classify_command(["git", "clean", "-fd"]) is CommandClass.DANGEROUS
    assert classify_command(["git", "rm", "x.py"]) is CommandClass.DANGEROUS


def test_exe_extension_and_case_insensitive() -> None:
    assert classify_command(["DEL.EXE", "x"]) is CommandClass.DANGEROUS
    assert classify_command(["Python", "-V"]) is CommandClass.SAFE
    assert classify_command(["GIT", "status"]) is CommandClass.SAFE
