"""Architecture tests for the framework-independent domain boundary."""

import ast
import sys
from pathlib import Path

import intelligence

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "domain"
APPLICATION_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "application"
INFRASTRUCTURE_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "infrastructure"
CONNECTORS_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "connectors"
SIMULATED_CONNECTORS_ROOT = CONNECTORS_ROOT / "simulated"
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
FORBIDDEN_CONNECTOR_IMPORT_PREFIXES = {
    "alembic",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "intelligence.application",
    "intelligence.claims",
    "intelligence.documents",
    "intelligence.entity_resolution",
    "intelligence.evidence",
    "intelligence.infrastructure",
    "intelligence.orchestration",
    "intelligence.reporting",
    "intelligence.risk",
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


def test_domain_never_imports_connector_contracts() -> None:
    """Dependency direction remains connectors -> stable domain types only."""

    violations: list[str] = []
    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "intelligence.connectors" in source:
            violations.append(path.name)

    assert violations == []


def test_connectors_import_only_standard_library_domain_and_own_contracts() -> None:
    """Connector contracts stay independent from frameworks and downstream layers."""

    violations: list[str] = []
    for path in sorted(CONNECTORS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                root = module.partition(".")[0]
                is_allowed_internal = module.startswith(
                    ("intelligence.connectors", "intelligence.domain")
                )
                is_forbidden = any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_CONNECTOR_IMPORT_PREFIXES
                )
                if is_forbidden or (
                    root not in sys.stdlib_module_names and not is_allowed_internal
                ):
                    violations.append(f"{path.relative_to(CONNECTORS_ROOT)} -> {module}")

    assert violations == []


def test_connectors_have_no_network_database_or_import_time_io_surface() -> None:
    """Connector contracts and simulators cannot open external I/O surfaces."""

    forbidden_import_roots = FORBIDDEN_NETWORK_IMPORTS | {
        "alembic",
        "importlib",
        "os",
        "pathlib",
        "pkgutil",
        "sqlalchemy",
        "subprocess",
    }
    forbidden_calls = {
        "connect",
        "create_engine",
        "entry_points",
        "glob",
        "iterdir",
        "open",
        "read_bytes",
        "read_text",
        "rglob",
        "socket",
    }
    violations: list[str] = []
    for path in sorted(CONNECTORS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_import_roots:
                    violations.append(f"{path.name} -> import {module}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                else:
                    continue
                if call_name in forbidden_calls:
                    violations.append(f"{path.name} -> call {call_name}")

    assert violations == []


def test_f32_allows_only_simulators_and_preserves_existing_migrations() -> None:
    """F3.2 permits simulators while runners, real adapters, and schema stay absent."""

    forbidden_parts = {"adapters", "execution", "http", "real", "runner"}
    assert all(
        forbidden_parts.isdisjoint(path.relative_to(CONNECTORS_ROOT).parts)
        for path in CONNECTORS_ROOT.rglob("*")
    )

    migration_root = Path(__file__).parents[2] / "migrations" / "versions"
    assert {path.name for path in migration_root.glob("*.py")} == {
        "20260728_01_create_initial_domain_schema.py",
        "20260728_02_create_identities_memberships_audit.py",
    }


def test_simulated_connectors_use_no_io_clock_environment_or_randomness() -> None:
    """Synthetic outcomes use fixed values and never invoke F3.3 or external mechanisms."""

    forbidden_import_roots = {
        "alembic",
        "asyncio",
        "http",
        "httpx",
        "importlib",
        "os",
        "pathlib",
        "pkgutil",
        "psycopg",
        "random",
        "requests",
        "secrets",
        "socket",
        "sqlalchemy",
        "subprocess",
        "time",
        "urllib",
        "uuid",
    }
    forbidden_calls = {
        "Popen",
        "call",
        "check_call",
        "check_output",
        "connect",
        "create_engine",
        "entry_points",
        "getenv",
        "glob",
        "iterdir",
        "monotonic",
        "now",
        "open",
        "perf_counter",
        "popen",
        "read_bytes",
        "read_text",
        "rglob",
        "run",
        "sleep",
        "socket",
        "system",
        "time",
        "timeout",
        "today",
        "utcnow",
        "uuid1",
        "uuid4",
        "wait_for",
        "write_bytes",
        "write_text",
    }
    violations: list[str] = []
    for path in sorted(SIMULATED_CONNECTORS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_import_roots:
                    violations.append(f"{path.name} -> import {module}")
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                violations.append(f"{path.name} -> environment access")
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if call_name in forbidden_calls or call_name.startswith(("rand", "urandom")):
                violations.append(f"{path.name} -> call {call_name}")

    assert violations == []


def test_simulated_connectors_have_no_mutable_module_level_fixture_collections() -> None:
    """Scenario fixtures cannot accumulate state through mutable module globals."""

    violations: list[str] = []
    for path in sorted(SIMULATED_CONNECTORS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for statement in tree.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(
                statement.value,
                (ast.Dict, ast.List, ast.Set),
            ):
                targets = (
                    statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                )
                assigned_names = {
                    node.id
                    for target in targets
                    for node in ast.walk(target)
                    if isinstance(node, ast.Name)
                }
                if assigned_names != {"__all__"}:
                    violations.append(f"{path.name}:{statement.lineno}")

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
                is_internal = (
                    module.startswith("intelligence.application")
                    or module.startswith("intelligence.domain")
                    or module.startswith("intelligence.infrastructure")
                )
                if (
                    root not in sys.stdlib_module_names
                    and root not in ALLOWED_INFRASTRUCTURE_IMPORTS
                    and not is_internal
                ):
                    violations.append(f"{path.relative_to(INFRASTRUCTURE_ROOT)} -> {module}")

    assert violations == []


def test_application_imports_only_domain_and_application_contracts() -> None:
    """Application ports cannot depend on infrastructure or database frameworks."""

    violations: list[str] = []
    for path in sorted(APPLICATION_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                root = module.partition(".")[0]
                is_internal = module.startswith("intelligence.application") or module.startswith(
                    "intelligence.domain"
                )
                if root not in sys.stdlib_module_names and not is_internal:
                    violations.append(f"{path.relative_to(APPLICATION_ROOT)} -> {module}")

    assert violations == []


def test_persistence_ports_do_not_import_database_implementations() -> None:
    """Port modules remain free of SQLAlchemy, Alembic, and PostgreSQL adapters."""

    ports_root = APPLICATION_ROOT / "ports"
    violations: list[str] = []
    for path in sorted(ports_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in {"alembic", "sqlalchemy"} or module.startswith(
                    "intelligence.infrastructure"
                ):
                    violations.append(f"{path.relative_to(ports_root)} -> {module}")

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


def test_source_modules_do_not_open_database_connections_during_import() -> None:
    """Engine creation and connection opening must stay inside explicit callables."""

    source_root = Path(__file__).parents[2] / "src"
    forbidden_call_names = {"begin", "connect", "create_engine"}
    violations: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for statement in tree.body:
            if isinstance(statement, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef)):
                continue
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                else:
                    continue
                if call_name in forbidden_call_names:
                    violations.append(f"{path.relative_to(source_root)} -> {call_name}")

    assert violations == []


def test_repository_adapters_never_commit_transactions() -> None:
    """Only the Unit of Work may decide the transaction outcome."""

    repository_path = INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py"
    tree = ast.parse(
        repository_path.read_text(encoding="utf-8"),
        filename=str(repository_path),
    )
    commit_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    ]

    assert commit_calls == []


def test_repository_adapters_never_roll_back_transactions() -> None:
    """Only the Unit of Work may roll back the shared transaction."""

    repository_path = INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py"
    tree = ast.parse(repository_path.read_text(encoding="utf-8"), filename=str(repository_path))
    rollback_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rollback"
    ]

    assert rollback_calls == []


def test_audit_repository_surfaces_are_append_only() -> None:
    """The audit port and adapter expose insertion, never mutation or deletion."""

    paths_and_classes = (
        (
            APPLICATION_ROOT / "ports" / "repositories.py",
            "AuditEventRepository",
        ),
        (
            INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py",
            "PostgreSQLAuditEventRepository",
        ),
    )
    for path, class_name in paths_and_classes:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        class_node = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        methods = {
            node.name
            for node in class_node.body
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        }
        assert "add" in methods
        assert methods.isdisjoint({"delete", "replace", "save", "update"})


def test_f242_application_services_do_not_import_sql_or_infrastructure() -> None:
    """Tenant-scoped services coordinate ports without embedding persistence."""

    services_root = APPLICATION_ROOT / "services"
    violations: list[str] = []
    for path in sorted(services_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        if "SELECT " in source.upper() or "UPDATE " in source.upper():
            violations.append(f"{path.name} -> SQL text")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] == "sqlalchemy" or module.startswith(
                    "intelligence.infrastructure"
                ):
                    violations.append(f"{path.name} -> {module}")

    assert violations == []


def test_authorization_policy_has_no_io_or_repository_access() -> None:
    """The role matrix remains a pure deterministic class."""

    path = APPLICATION_ROOT / "authorization.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    policy = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RolePermissionPolicy"
    )
    forbidden_calls = {
        node.func.attr
        for node in ast.walk(policy)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert forbidden_calls.isdisjoint({"add", "commit", "execute", "get", "rollback"})


def test_repositories_do_not_import_application_permissions_or_authorization() -> None:
    """Repository adapters filter persistence vocabulary but never decide access."""

    path = INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py"
    source = path.read_text(encoding="utf-8")

    assert "Permission" not in source
    assert "AuthorizedActor" not in source
    assert "ActorContext" not in source
    assert "AuthorizationDeniedError" not in source


def test_api_has_no_f242_services_authentication_or_new_endpoints() -> None:
    """F2.4.2 is application-only and does not expose an HTTP surface."""

    violations: list[str] = []
    for path in sorted(API_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "intelligence.application.services" in source:
            violations.append(f"{path.name} -> application services")
        if any(marker in source.lower() for marker in ("jwt", "oauth", "middleware")):
            violations.append(f"{path.name} -> authentication surface")

    assert violations == []
