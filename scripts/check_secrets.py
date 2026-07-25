"""Small dependency-free scanner for obvious committed secret patterns."""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from typing import Final, cast

MAX_FILE_SIZE: Final = 1_000_000
IGNORED_DIRECTORIES: Final = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
)
TEXT_SUFFIXES: Final = frozenset(
    {
        "",
        ".css",
        ".env",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)

_PRIVATE_KEY_MARKER = "-" * 5 + "BEGIN "
SECRET_PATTERNS: Final[tuple[tuple[str, Pattern[str]], ...]] = (
    (
        "private-key",
        re.compile(re.escape(_PRIVATE_KEY_MARKER) + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-+"),
    ),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}\b")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+\-=]{8,}"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """A possible secret found in a repository text file."""

    path: Path
    line_number: int
    pattern_name: str


def iter_candidate_files(root: Path) -> Iterator[Path]:
    """Yield small UTF-8-oriented repository files in a stable order."""

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > MAX_FILE_SIZE:
            continue
        yield path


def scan_repository(root: Path) -> list[Finding]:
    """Return possible secrets without printing their values."""

    findings: list[Finding] = []
    for path in iter_candidate_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern_name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(path, line_number, pattern_name))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scanner and return a process-compatible status code."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    namespace = parser.parse_args(argv)
    root = Path(cast(str, namespace.root)).resolve()
    findings = scan_repository(root)

    if findings:
        for finding in findings:
            relative_path = finding.path.relative_to(root)
            print(f"{relative_path}:{finding.line_number}: possible {finding.pattern_name}")
        return 1

    print("Secret scan passed: no obvious credential values found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
