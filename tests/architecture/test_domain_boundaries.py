"""Architecture tests for the framework-independent domain boundary."""

import ast
import sys
from pathlib import Path

import intelligence

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "domain"
INFRASTRUCTURE_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "infrastructure"
API_ROOT = Path(__file__).parents[2] / "apps" / "api"
ALLOWED_INTERNAL_PREFIX = "intelligence.domain"
ALLOWED_INFRASTRUCTURE_IMPORTS = {
    "sqlalchemy",
}
FORBIDDEN_NETWORK_IMPORTS = {
    "httpx",
    "requests",
    "socket",
    "urllib",
}


def forbidden_imports(path: Path) -> set[str]:
    """Collect imports that escape the standard library and domain boundary."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_allowed_absolute_import(alias.name):
                    violations.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1:
                continue
            if node.level > 1:
                violations.add(f"relative import with level {node.level}")
            elif node.module and not _is_allowed_absolute_import(node.module):
                violations.add(node.module)
    return violations


def _is_allowed_absolute_import(module: str) -> bool:
    root = module.partition(".")[0]
    return root in sys.stdlib_module_names or (
        module == ALLOWED_INTERNAL_PREFIX or module.startswith(f"{ALLOWED_INTERNAL_PREFIX}.")
    )


def test_core_package_is_importable_without_frameworks() -> None:
    """The core package imports without exposing framework dependencies."""

    assert intelligence.__all__ == ()


def test_domain_imports_only_standard_library_or_core_packages() -> None:
    """The domain cannot import frameworks, infrastructure, or other core layers."""

    violations: list[str] = []
    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        for imported_module in forbidden_imports(path):
            violations.append(f"{path.relative_to(DOMAIN_ROOT)} -> {imported_module}")

    assert violations == []


def test_boundary_checker_rejects_external_and_cross_layer_imports(tmp_path: Path) -> None:
    """The checker itself detects both categories of forbidden dependency."""

    source = tmp_path / "invalid_domain.py"
    source.write_text(
        "from fastapi import FastAPI\n"
        "from intelligence.application import service\n"
        "from ..infrastructure import repository\n",
        encoding="utf-8",
    )

    assert forbidden_imports(source) == {
        "fastapi",
        "intelligence.application",
        "relative import with level 2",
    }


def test_postgresql_infrastructure_imports_only_approved_layers() -> None:
    """Persistence may use SQLAlchemy and domain vocabulary, not other adapters."""

    violations: list[str] = []
    for path in sorted(INFRASTRUCTURE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.append(node.module)
            for module in modules:
                root = module.partition(".")[0]
                is_internal = module.startswith("intelligence.domain") or module.startswith(
                    "intelligence.infrastructure"
                )
                if (
                    root not in sys.stdlib_module_names
                    and root not in ALLOWED_INFRASTRUCTURE_IMPORTS
                    and not is_internal
                ):
                    violations.append(f"{path.relative_to(INFRASTRUCTURE_ROOT)} -> {module}")

    assert violations == []


def test_api_does_not_import_persistence_or_database_frameworks() -> None:
    """Composition has no direct table access before an application port exists."""

    violations: list[str] = []
    for path in sorted(API_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in {"alembic", "sqlalchemy"} or module.startswith(
                    "intelligence.infrastructure.persistence"
                ):
                    violations.append(f"{path.relative_to(API_ROOT)} -> {module}")

    assert violations == []


def test_new_persistence_modules_have_no_network_client_imports() -> None:
    """Schema and migrations cannot introduce outbound-call mechanisms."""

    roots = (INFRASTRUCTURE_ROOT, Path(__file__).parents[2] / "migrations")
    violations: list[str] = []
    for root_path in roots:
        for path in sorted(root_path.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    modules = []
                for module in modules:
                    if module.partition(".")[0] in FORBIDDEN_NETWORK_IMPORTS:
                        violations.append(f"{path.relative_to(root_path)} -> {module}")

    assert violations == []
