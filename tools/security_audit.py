"""Public-repository security policy checks for Luma Atelier.

The checks are deliberately local and deterministic: they never upload source
code, discovered values, or file contents.  Findings identify only the policy,
file, and line so a suspected secret is not repeated in logs.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".cmd",
    ".css",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".spec",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {".gitattributes", ".gitignore", "Dockerfile", "LICENSE"}
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}

NETWORK_MODULES = {
    "aiohttp",
    "ftplib",
    "http",
    "httpx",
    "requests",
    "smtplib",
    "socket",
    "telnetlib",
    "urllib",
    "websocket",
    "websockets",
}

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[opusr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|"
        r"client[_-]?secret|secret[_-]?key|password)\b\s*[:=]\s*"
        r"[\"'][^\"'\r\n]{8,}[\"']"
    ),
)

WINDOWS_USER_PATH = re.compile(
    r"(?i)\b[A-Z]:\\Users\\(?!<|%|\{|\$)[^\\\s]+\\"
)
POSIX_USER_PATH = re.compile(r"/(?:Users|home)/(?!<|\{|\$)[^/\s]+/")


@dataclass(frozen=True, order=True)
class AuditFinding:
    code: str
    path: Path
    line: int
    message: str


def _git_candidates(root: Path) -> list[Path] | None:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root}",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return [root / Path(raw.decode("utf-8"))
            for raw in result.stdout.split(b"\0") if raw]


def _candidate_text_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    candidates = _git_candidates(root)
    if candidates is None:
        candidates = [path for path in root.rglob("*") if path.is_file()]

    for path in sorted(candidates):
        try:
            relative = path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def audit_secrets(root: Path) -> list[AuditFinding]:
    root = root.resolve()
    findings: list[AuditFinding] = []
    for path in _candidate_text_files(root):
        text = _read_text(path)
        if text is None:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                findings.append(AuditFinding(
                    code="secret",
                    path=path.relative_to(root),
                    line=line_number,
                    message="Possible credential material; value redacted",
                ))
    return findings


def audit_network_imports(root: Path) -> list[AuditFinding]:
    root = root.resolve()
    source_root = root / "src" / "luma_atelier"
    findings: list[AuditFinding] = []
    if not source_root.is_dir():
        return findings

    for path in sorted(source_root.rglob("*.py")):
        text = _read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [item.name.split(".", 1)[0] for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".", 1)[0]]
            for module in modules:
                if module in NETWORK_MODULES:
                    findings.append(AuditFinding(
                        code="network-import",
                        path=path.relative_to(root),
                        line=node.lineno,
                        message=f"Application imports network-capable module: {module}",
                    ))
    return findings


def audit_personal_paths(root: Path) -> list[AuditFinding]:
    root = root.resolve()
    findings: list[AuditFinding] = []
    for path in _candidate_text_files(root):
        text = _read_text(path)
        if text is None:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            normalized = line.replace("\\\\", "\\")
            if WINDOWS_USER_PATH.search(normalized) or POSIX_USER_PATH.search(line):
                findings.append(AuditFinding(
                    code="personal-path",
                    path=path.relative_to(root),
                    line=line_number,
                    message="Personal home-directory path must use a placeholder",
                ))
    return findings


def audit_repository(root: Path) -> list[AuditFinding]:
    findings = [
        *audit_secrets(root),
        *audit_network_imports(root),
        *audit_personal_paths(root),
    ]
    return sorted(findings, key=lambda item: (str(item.path), item.line, item.code))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan publishable files without sending source off-device."
    )
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    findings = audit_repository(args.root)
    for finding in findings:
        print(
            f"{finding.code}: {finding.path}:{finding.line}: {finding.message}"
        )
    if findings:
        print(f"Security audit failed with {len(findings)} finding(s).")
        return 1
    print("Security audit passed: no secret, network import, or personal path findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
