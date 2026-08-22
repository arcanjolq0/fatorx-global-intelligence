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
EXECUTION_CONNECTORS_ROOT = CONNECTORS_ROOT / "execution"
EXECUTION_CONNECTOR_TESTS_ROOT = Path(__file__).parents[1] / "connectors" / "execution"
ENTITY_RESOLUTION_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "entity_resolution"
EVIDENCE_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "evidence"
CLAIMS_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "claims"
ORCHESTRATION_ROOT = Path(__file__).parents[2] / "src" / "intelligence" / "orchestration"
F41_LIFECYCLE_PATHS = (
    DOMAIN_ROOT / "investigation_inputs.py",
    DOMAIN_ROOT / "investigations.py",
    APPLICATION_ROOT / "investigation_lifecycle.py",
    APPLICATION_ROOT / "services" / "investigations.py",
)
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


def test_f33_allows_simulation_and_single_operation_execution_without_later_phases() -> None:
    """F4.6 adds only its receipt schema while real connector adapters stay absent."""

    forbidden_parts = {"adapters", "http", "real"}
    assert all(
        forbidden_parts.isdisjoint(path.relative_to(CONNECTORS_ROOT).parts)
        for path in CONNECTORS_ROOT.rglob("*")
    )

    migration_root = Path(__file__).parents[2] / "migrations" / "versions"
    assert {path.name for path in migration_root.glob("*.py")} == {
        "20260728_01_create_initial_domain_schema.py",
        "20260728_02_create_identities_memberships_audit.py",
        "20260729_03_add_investigation_lifecycle_foundation.py",
        "20260729_04_add_entity_candidate_review_foundation.py",
        "20260801_05_add_entity_confirmation_decision.py",
        "20260801_06_add_investigation_planning.py",
        "20260801_07_harden_plan_continuity_audit_cost.py",
        "20260802_08_add_collection_activation.py",
        "20260802_09_harden_collection_activation_history.py",
        "20260811_10_add_direct_collection_execution.py",
        "20260814_11_add_canonical_evidence_core.py",
        "20260821_12_add_claims_contextual_evidence.py",
        "20260822_13_add_global_evidence_admissibility.py",
    }


def test_execution_controls_have_no_external_io_or_forbidden_mechanisms() -> None:
    """The F3.3 runner uses only local asyncio and the explicitly allowed monotonic clock."""

    forbidden_import_roots = {
        "alembic",
        "http",
        "httpx",
        "importlib",
        "logging",
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
        "urllib",
    }
    forbidden_calls = {
        "Popen",
        "basicConfig",
        "call",
        "check_call",
        "check_output",
        "connect",
        "create_engine",
        "entry_points",
        "getenv",
        "glob",
        "iterdir",
        "open",
        "perf_counter",
        "popen",
        "read_bytes",
        "read_text",
        "rglob",
        "socket",
        "system",
        "time",
        "time_ns",
        "write_bytes",
        "write_text",
    }
    violations: list[str] = []
    for path in sorted(EXECUTION_CONNECTORS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_import_roots or module.startswith("tests"):
                    violations.append(f"{path.name} -> import {module}")
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                violations.append(f"{path.name} -> environment access")
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(f"{path.name} -> Any")
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
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"date", "datetime", "time"}
                and node.func.attr in {"now", "today", "utcnow"}
            ):
                violations.append(f"{path.name} -> wall-clock call {node.func.attr}")
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "asyncio"
                and node.func.attr == "sleep"
                and path.name != "ports.py"
            ):
                violations.append(f"{path.name} -> direct asyncio.sleep")

    assert violations == []


def test_execution_tests_use_events_and_never_real_sleep_calls() -> None:
    """Race tests synchronize by asyncio primitives without timing guesses."""

    violations: list[str] = []
    for path in sorted(EXECUTION_CONNECTOR_TESTS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if call_name == "sleep":
                violations.append(f"{path.name}:{node.lineno}")

    assert violations == []


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
                    or module.startswith("intelligence.claims")
                    or module.startswith("intelligence.connectors")
                    or module.startswith("intelligence.domain")
                    or module.startswith("intelligence.entity_resolution")
                    or module.startswith("intelligence.evidence")
                    or module.startswith("intelligence.infrastructure")
                    or module.startswith("intelligence.orchestration")
                )
                if (
                    root not in sys.stdlib_module_names
                    and root not in ALLOWED_INFRASTRUCTURE_IMPORTS
                    and not is_internal
                ):
                    violations.append(f"{path.relative_to(INFRASTRUCTURE_ROOT)} -> {module}")

    assert violations == []


def test_application_imports_only_domain_and_application_contracts() -> None:
    """Only the explicit F4.6 boundary may consume connector contracts and runner."""

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
                relative_path = path.relative_to(APPLICATION_ROOT).as_posix()
                is_f46_connector_boundary = relative_path in {
                    "collection_execution.py",
                    "services/collection_execution.py",
                } and module.startswith("intelligence.connectors")
                is_internal = module.startswith(
                    (
                        "intelligence.application",
                        "intelligence.claims",
                        "intelligence.domain",
                        "intelligence.entity_resolution",
                        "intelligence.evidence",
                        "intelligence.orchestration",
                    )
                )
                if (
                    root not in sys.stdlib_module_names
                    and not is_internal
                    and not is_f46_connector_boundary
                ):
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


def test_f41_transition_ledger_surfaces_are_append_only() -> None:
    """The durable command ledger exposes locking, lookup, and append only."""

    paths_and_classes = (
        (
            APPLICATION_ROOT / "ports" / "repositories.py",
            "InvestigationTransitionRepository",
        ),
        (
            INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py",
            "PostgreSQLInvestigationTransitionRepository",
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
        assert {"acquire_command_lock", "add", "get_by_command"} <= methods
        assert methods.isdisjoint({"delete", "replace", "save", "update"})


def test_lifecycle_through_f42_has_no_runner_io_environment_or_later_phase_imports() -> None:
    """Lifecycle remains synchronous core coordination without external I/O."""

    forbidden_roots = {
        "asyncio",
        "http",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_internal_prefixes = {
        "intelligence.claims",
        "intelligence.connectors",
        "intelligence.evidence",
        "intelligence.orchestration",
        "intelligence.reporting",
        "intelligence.risk",
    }
    forbidden_calls = {
        "Popen",
        "connect",
        "getenv",
        "open",
        "read_bytes",
        "read_text",
        "run",
        "socket",
        "system",
        "write_bytes",
        "write_text",
    }
    violations: list[str] = []
    for path in F41_LIFECYCLE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_roots or any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_internal_prefixes
                ):
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
            if call_name in forbidden_calls:
                violations.append(f"{path.name} -> call {call_name}")

    assert violations == []


def test_lifecycle_exposes_only_specific_commands_without_generic_destination() -> None:
    """Lifecycle growth requires a named command instead of transition_to(state)."""

    investigation_tree = ast.parse((DOMAIN_ROOT / "investigations.py").read_text(encoding="utf-8"))
    service_tree = ast.parse(
        (APPLICATION_ROOT / "services" / "investigations.py").read_text(encoding="utf-8")
    )
    investigation_class = next(
        node
        for node in investigation_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Investigation"
    )
    service_class = next(
        node
        for node in service_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "InvestigationService"
    )
    domain_public_methods = {
        node.name
        for node in investigation_class.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and not node.name.startswith("_")
    }
    service_public_methods = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and not node.name.startswith("_")
    }

    assert {"start_identification", "cancel", "request_entity_confirmation", "confirm_entity"} <= (
        domain_public_methods
    )
    assert {
        "start_identification",
        "cancel_investigation",
        "request_entity_confirmation",
    } <= service_public_methods
    assert domain_public_methods.isdisjoint({"set_state", "transition", "transition_to"})
    assert service_public_methods.isdisjoint({"set_state", "transition", "transition_to"})


def test_f52_does_not_create_post_claim_packages_or_sensitive_audit_payloads() -> None:
    """F5.2 adds Claims, but no later risk or reporting domains."""

    source_packages = {
        path.name for path in (Path(__file__).parents[2] / "src" / "intelligence").iterdir()
    }
    assert source_packages.isdisjoint(
        {
            "candidates",
            "jobs",
            "planner",
            "reporting",
            "risk",
        }
    )
    audit_source = (APPLICATION_ROOT / "audit.py").read_text(encoding="utf-8").lower()
    assert "input_snapshot" not in audit_source
    assert "identification_input" not in audit_source


def test_f51_evidence_core_is_pure_and_has_no_later_phase_capabilities() -> None:
    """Canonical evidence has no I/O, claims, risk, reports, models, or workers."""

    forbidden_roots = {
        "alembic",
        "asyncio",
        "fastapi",
        "httpx",
        "os",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
    }
    forbidden_internal = {
        "intelligence.claims",
        "intelligence.connectors",
        "intelligence.infrastructure",
        "intelligence.reporting",
        "intelligence.risk",
    }
    violations: list[str] = []
    for path in sorted(EVIDENCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_roots or any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_internal
                ):
                    violations.append(f"{path.name} -> {module}")
    assert violations == []


def test_f52_claims_core_is_pure_and_has_no_later_phase_capabilities() -> None:
    """Claims use stable domain types without I/O, policy, persistence, risk, or reports."""

    forbidden_roots = {
        "alembic",
        "asyncio",
        "fastapi",
        "httpx",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
    }
    forbidden_internal = {
        "intelligence.application",
        "intelligence.connectors",
        "intelligence.evidence",
        "intelligence.infrastructure",
        "intelligence.interfaces",
        "intelligence.reporting",
        "intelligence.risk",
    }
    violations: list[str] = []
    for path in sorted(CLAIMS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if module.partition(".")[0] in forbidden_roots or any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_internal
                ):
                    violations.append(f"{path.name} -> {module}")
    assert violations == []


def test_f42_entity_resolution_is_pure_closed_and_connector_independent() -> None:
    """The matcher has no I/O, clock, randomness, framework, or downstream dependencies."""

    forbidden_import_roots = {
        "alembic",
        "asyncio",
        "fastapi",
        "http",
        "httpx",
        "os",
        "pathlib",
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
    forbidden_internal_prefixes = {
        "intelligence.application",
        "intelligence.claims",
        "intelligence.connectors",
        "intelligence.documents",
        "intelligence.evidence",
        "intelligence.infrastructure",
        "intelligence.orchestration",
        "intelligence.reporting",
        "intelligence.risk",
    }
    forbidden_calls = {
        "connect",
        "getenv",
        "now",
        "open",
        "read_bytes",
        "read_text",
        "sleep",
        "today",
        "utcnow",
        "write_bytes",
        "write_text",
    }
    violations: list[str] = []
    for path in sorted(ENTITY_RESOLUTION_ROOT.rglob("*.py")):
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
                if module.partition(".")[0] in forbidden_import_roots or any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_internal_prefixes
                ):
                    violations.append(f"{path.name} -> import {module}")
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                violations.append(f"{path.name}:{node.lineno} -> float")
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if call_name in forbidden_calls or call_name.startswith(("rand", "urandom")):
                violations.append(f"{path.name}:{node.lineno} -> call {call_name}")
        assert "CandidateObservation" not in source
        assert "ConnectorOutcome" not in source
        assert "ConnectorProtocol" not in source

    assert violations == []


def test_f43_confirmation_is_explicit_and_candidate_batches_remain_immutable() -> None:
    """F4.3 adds explicit confirmation without rejection-all or batch mutation."""

    f42_source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (ENTITY_RESOLUTION_ROOT, APPLICATION_ROOT)
        for path in sorted(root.rglob("*.py"))
    )
    assert "ConfirmEntityCandidate" in f42_source
    assert "RejectAllCandidates" not in f42_source

    paths_and_classes = (
        (
            APPLICATION_ROOT / "ports" / "repositories.py",
            "EntityCandidateBatchRepository",
        ),
        (
            INFRASTRUCTURE_ROOT / "persistence" / "postgresql" / "repositories.py",
            "PostgreSQLEntityCandidateBatchRepository",
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
        assert {"add", "get"} <= methods
        assert methods.isdisjoint({"delete", "replace", "save", "update"})


def test_f43_confirmation_has_no_auto_selection_or_later_phase_capability() -> None:
    """Confirmation consumes one explicit ID and cannot plan, link, reject, or run I/O."""

    command_path = APPLICATION_ROOT / "entity_confirmation.py"
    service_path = APPLICATION_ROOT / "services" / "entity_confirmation.py"
    source = command_path.read_text(encoding="utf-8") + service_path.read_text(encoding="utf-8")
    for forbidden_name in (
        "CreatePlan",
        "InvestigationPlan",
        "LinkExistingCompany",
        "MergeCompany",
        "PlannedCapability",
        "RejectAllCandidates",
        "RejectCandidate",
    ):
        assert forbidden_name not in source

    service_tree = ast.parse(service_path.read_text(encoding="utf-8"), filename=str(service_path))
    forbidden_calls = {
        "evaluate_candidate_batch",
        "getenv",
        "open",
        "sleep",
        "system",
    }
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(service_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert calls.isdisjoint(forbidden_calls)
    assert all(
        not module.startswith(
            (
                "intelligence.claims",
                "intelligence.connectors",
                "intelligence.evidence",
                "intelligence.orchestration",
                "intelligence.reporting",
                "intelligence.risk",
            )
        )
        for node in ast.walk(service_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for module in (node.module,)
    )

    command_tree = ast.parse(command_path.read_text(encoding="utf-8"), filename=str(command_path))
    command_class = next(
        node
        for node in command_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ConfirmEntityCandidate"
    )
    command_fields = {
        target.id
        for node in command_class.body
        if isinstance(node, ast.AnnAssign) and isinstance((target := node.target), ast.Name)
    }
    assert command_fields == {
        "command_id",
        "investigation_id",
        "expected_state_version",
        "candidate_batch_id",
        "candidate_id",
        "review_reason",
        "materialization_policy",
        "schema_version",
    }


def test_f44_planning_is_pure_and_does_not_execute_or_advance_lifecycle() -> None:
    """Planning uses static descriptors without I/O, runners, or COLLECTING transition."""

    planning_path = ORCHESTRATION_ROOT / "planning.py"
    service_path = APPLICATION_ROOT / "services" / "investigation_planning.py"
    planning_source = planning_path.read_text(encoding="utf-8")
    service_source = service_path.read_text(encoding="utf-8")
    planning_tree = ast.parse(planning_source, filename=str(planning_path))
    service_tree = ast.parse(service_source, filename=str(service_path))
    forbidden_import_roots = {
        "alembic",
        "asyncio",
        "fastapi",
        "http",
        "httpx",
        "os",
        "pathlib",
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
    imports = {
        module
        for node in ast.walk(planning_tree)
        for module in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
            if isinstance(node, ast.ImportFrom) and node.module
            else []
        )
    }
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(planning_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }

    assert all(module.partition(".")[0] not in forbidden_import_roots for module in imports)
    assert not any(
        isinstance(node, ast.Constant) and isinstance(node.value, float)
        for node in ast.walk(planning_tree)
    )
    assert calls.isdisjoint({"connect", "execute", "getenv", "open", "sleep", "today", "utcnow"})
    assert "COLLECTING" not in service_source
    assert "compare_and_swap" not in service_source
    service_calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(service_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert service_calls.isdisjoint(
        {"execute", "fetch_details", "fetch_document", "run", "search", "transition"}
    )


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


def test_f45_activation_materializes_only_and_never_calls_connectors_or_runners() -> None:
    """F4.5 may persist a manifest and COLLECTING transition, but cannot execute it."""

    activation_paths = (
        ORCHESTRATION_ROOT / "collection_activation.py",
        APPLICATION_ROOT / "collection_activation.py",
        APPLICATION_ROOT / "services" / "collection_activation.py",
    )
    forbidden_imports = {
        "intelligence.connectors.execution",
        "intelligence.connectors.registry",
        "intelligence.connectors.simulated",
    }
    forbidden_calls = {
        "execute",
        "run",
        "run_operation",
        "submit",
        "sleep",
        "retry",
    }
    violations: list[str] = []
    for path in activation_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_imports
                ):
                    violations.append(f"{path.name} -> import {module}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                else:
                    continue
                if name in forbidden_calls:
                    violations.append(f"{path.name}:{node.lineno} -> call {name}")
    assert violations == []

    repository_path = APPLICATION_ROOT / "ports" / "repositories.py"
    repository_tree = ast.parse(
        repository_path.read_text(encoding="utf-8"), filename=str(repository_path)
    )
    collection_repository = next(
        node
        for node in repository_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CollectionRunRepository"
    )
    methods = {
        node.name
        for node in collection_repository.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    assert "add" in methods
    assert methods.isdisjoint({"delete", "replace", "save", "update"})


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
