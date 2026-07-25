"""Architecture tests for the framework-independent domain boundary."""

import ast
import sys
from pathlib import Path

import intelligence

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "domain"
ALLOWED_INTERNAL_ROOT = "intelligence"


def imported_roots(path: Path) -> set[str]:
    """Collect absolute top-level imports from a Python source file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.partition(".")[0])
    return roots


def test_core_package_is_importable_without_frameworks() -> None:
    """The core package imports without exposing framework dependencies."""

    assert intelligence.__all__ == ()


def test_domain_imports_only_standard_library_or_core_packages() -> None:
    """The domain cannot import FastAPI or any other external framework."""

    violations: list[str] = []
    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        for imported_root in imported_roots(path):
            if (
                imported_root not in sys.stdlib_module_names
                and imported_root != ALLOWED_INTERNAL_ROOT
            ):
                violations.append(f"{path.relative_to(DOMAIN_ROOT)} -> {imported_root}")

    assert violations == []
