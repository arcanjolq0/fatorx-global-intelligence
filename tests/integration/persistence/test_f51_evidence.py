"""F5.1 PostgreSQL evidence round-trip, tenancy, lifecycle, and tamper tests."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from typing import cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    EvidenceAlreadyRevokedError,
    EvidenceVersionConflictError,
    InvalidEvidenceContextError,
    PersistenceDataError,
    ResourceNotFoundError,
)
from intelligence.application.evidence import CorrectEvidence, RegisterEvidence, RevokeEvidence
from intelligence.application.services.entity_confirmation import EntityConfirmationService
from intelligence.application.services.evidence import EvidenceService
from intelligence.domain.identifiers import EvidenceCommandId, InvestigationId
from intelligence.domain.identities import MembershipRole
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceKind,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    JsonPointerLocator,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
)
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.evidence_tables import (
    evidence_artifact_table,
    evidence_lifecycle_event_table,
    evidence_table,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    investigation_table,
    workspace_membership_table,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from tests.integration.persistence.test_f43_entity_confirmation import (
    _command as confirmation_command,
)
from tests.integration.persistence.test_f43_entity_confirmation import _seed_waiting
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 14, 15, tzinfo=UTC)
ORIGINAL = b'{"company":{"name":"Empresa Exemplo S.A."}}'
LOCATED = b"Empresa Exemplo S.A."


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    database_url = require_safe_destructive_database_url()
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, "head")
    database_engine = create_postgresql_engine({"DATABASE_URL": database_url})
    try:
        yield database_engine
    finally:
        database_engine.dispose()
        alembic_command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE evidence_lifecycle_event, evidence, evidence_artifact, "
                "entity_resolution_decision, investigation_transition, audit_event, "
                "entity_candidate_dimension_score, entity_candidate, entity_candidate_batch, "
                "workspace_membership, user_account, investigation, company, workspace CASCADE"
            )
        )


def _seed_collecting(
    engine: Engine, *, owner: bool = False, label: str = "tenant-a"
) -> ActorContext:
    actor, waiting = _seed_waiting(engine, label)
    EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, confirmation_command(engine, actor, waiting))
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(state="COLLECTING", state_version=waiting.state_version + 2)
        )
        if owner:
            connection.execute(
                sa.update(workspace_membership_table)
                .where(
                    workspace_membership_table.c.workspace_id == actor.workspace_id.value,
                    workspace_membership_table.c.user_id == actor.user_id.value,
                )
                .values(role=MembershipRole.OWNER.value)
            )
    return actor


def _register_command(engine: Engine, actor: ActorContext) -> RegisterEvidence:
    with engine.connect() as connection:
        investigation_id = InvestigationId(
            cast(
                UUID,
                connection.scalar(
                    sa.select(investigation_table.c.id).where(
                        investigation_table.c.workspace_id == actor.workspace_id.value
                    )
                ),
            )
        )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        decision = unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id,
            investigation_id,
        )
        unit_of_work.commit()
    assert decision is not None
    return RegisterEvidence(
        command_id=EvidenceCommandId.new(),
        investigation_id=decision.investigation_id,
        entity_resolution_decision_id=decision.id,
        source_id="SYNTHETIC_REGISTRY",
        source_policy_version="SYNTHETIC_POLICY_V1",
        origin_type=ArtifactOriginType.FILE_IMPORT,
        origin_reference="fixture/company.json",
        origin_fingerprint=sha256(b"synthetic-origin").hexdigest(),
        acquisition_method="SYNTHETIC_IMPORT",
        acquisition_method_version="1.0.0",
        retrieved_at=NOW - timedelta(minutes=1),
        published_at=None,
        publication_absence_reason=PublicationAbsenceReason.NOT_PROVIDED,
        media_type="application/json",
        original_content=ORIGINAL,
        storage_mode=ArtifactStorageMode.EXCERPT_ONLY,
        storage_reference=None,
        retention_mode=RetentionMode.INDEFINITE,
        retention_until=None,
        display_mode=EvidenceDisplayMode.FULL,
        sensitivity=SensitivityClassification.INTERNAL,
        evidence_kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/name", response_sha256=sha256(ORIGINAL).hexdigest()
        ),
        located_content=LOCATED,
        content_original=LOCATED.decode(),
        extraction_method="JSON_POINTER",
        extraction_method_version="1.0.0",
    )


def test_postgresql_round_trip_replay_and_tenant_isolation(engine: Engine) -> None:
    actor = _seed_collecting(engine)
    command = _register_command(engine, actor)
    service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )

    result = service.register(actor, command)
    replay = service.register(actor, command)

    assert not result.replayed and replay.replayed
    assert replay.history == result.history
    with engine.connect() as connection:
        artifact = connection.execute(sa.select(evidence_artifact_table)).mappings().one()
        assert artifact["original_content_sha256"] == sha256(ORIGINAL).hexdigest()
        assert "original_content" not in artifact
        evidence = connection.execute(sa.select(evidence_table)).mappings().one()
        assert evidence["content_original"] == LOCATED.decode()
        assert evidence["admissibility_status"] == "PENDING"

    other_actor = _seed_collecting(engine, label="tenant-b")
    other_service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    with pytest.raises(ResourceNotFoundError):
        other_service.get_history(other_actor, result.history.latest.id)


def test_invalid_history_is_rejected_before_any_postgresql_evidence_write(
    engine: Engine,
) -> None:
    actor = _seed_collecting(engine)
    service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    invalid_registration = replace(
        _register_command(engine, actor),
        locator=JsonPointerLocator(
            pointer="/company/name",
            response_sha256=sha256(b"different artifact").hexdigest(),
        ),
    )

    with pytest.raises(InvalidEvidenceContextError):
        service.register(actor, invalid_registration)

    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(evidence_table)) == 0
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(evidence_artifact_table)) == 0
        )

    registered = service.register(actor, _register_command(engine, actor)).history
    invalid_correction = CorrectEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=registered.latest.id,
        expected_evidence_digest=registered.latest.evidence_digest,
        kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/legal_name",
            response_sha256=sha256(b"different artifact").hexdigest(),
        ),
        located_content=b"Empresa Exemplo Ltda.",
        content_original="Empresa Exemplo Ltda.",
        extraction_method="HUMAN_CORRECTION",
        extraction_method_version="1.0.0",
    )

    with pytest.raises(InvalidEvidenceContextError):
        service.correct(actor, invalid_correction)

    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(evidence_table)) == 1
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(evidence_lifecycle_event_table)
            )
            == 0
        )


def test_postgresql_correction_revocation_and_tamper_fail_closed(engine: Engine) -> None:
    actor = _seed_collecting(engine, owner=True)
    service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    registered = service.register(actor, _register_command(engine, actor))
    correction = CorrectEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=registered.history.latest.id,
        expected_evidence_digest=registered.history.latest.evidence_digest,
        kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/legal_name", response_sha256=sha256(ORIGINAL).hexdigest()
        ),
        located_content=b"Empresa Exemplo Ltda.",
        content_original="Empresa Exemplo Ltda.",
        extraction_method="HUMAN_CORRECTION",
        extraction_method_version="1.0.0",
    )
    corrected = service.correct(actor, correction)
    revoked = service.revoke(
        actor,
        RevokeEvidence(
            command_id=EvidenceCommandId.new(),
            evidence_id=corrected.history.latest.id,
            expected_evidence_digest=corrected.history.latest.evidence_digest,
            reason=EvidenceLifecycleReason.CONTENT_INVALID,
        ),
    )

    assert tuple(item.version for item in revoked.history.versions) == (1, 2)
    assert tuple(item.event_type for item in revoked.history.events) == (
        EvidenceLifecycleEventType.SUPERSEDED,
        EvidenceLifecycleEventType.REVOKED,
    )
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(evidence_table)) == 2
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(evidence_lifecycle_event_table)
            )
            == 2
        )
    with engine.begin() as connection:
        connection.execute(
            sa.update(evidence_table)
            .where(evidence_table.c.id == corrected.history.latest.id.value)
            .values(content_sha256="0" * 64)
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.evidence.get_history(actor.workspace_id, corrected.history.latest.id)


def test_database_rejects_cross_tenant_artifact_scope(engine: Engine) -> None:
    actor = _seed_collecting(engine)
    registered = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).register(actor, _register_command(engine, actor))
    other_actor = _seed_collecting(engine, label="tenant-b")

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(evidence_table)
            .where(evidence_table.c.id == registered.history.latest.id.value)
            .values(workspace_id=other_actor.workspace_id.value)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(evidence_artifact_table)
            .where(evidence_artifact_table.c.id == registered.history.artifact.id.value)
            .values(original_byte_length=0)
        )


def test_database_rejects_cross_tenant_version_and_event_links(engine: Engine) -> None:
    actor = _seed_collecting(engine, label="tenant-a")
    service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    first_tenant = service.register(actor, _register_command(engine, actor)).history
    other_actor = _seed_collecting(engine, label="tenant-b")
    other_service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    other_initial = other_service.register(
        other_actor, _register_command(engine, other_actor)
    ).history
    other_corrected = other_service.correct(
        other_actor,
        CorrectEvidence(
            command_id=EvidenceCommandId.new(),
            evidence_id=other_initial.latest.id,
            expected_evidence_digest=other_initial.latest.evidence_digest,
            kind=EvidenceKind.STRUCTURED_DATA,
            language="pt-BR",
            locator=JsonPointerLocator(
                pointer="/company/legal_name",
                response_sha256=sha256(ORIGINAL).hexdigest(),
            ),
            located_content=b"Empresa Exemplo Ltda.",
            content_original="Empresa Exemplo Ltda.",
            extraction_method="HUMAN_CORRECTION",
            extraction_method_version="1.0.0",
        ),
    ).history

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(evidence_table)
            .where(evidence_table.c.id == other_corrected.latest.id.value)
            .values(series_id=first_tenant.latest.series_id.value)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(evidence_lifecycle_event_table)
            .where(
                evidence_lifecycle_event_table.c.related_evidence_id
                == other_corrected.latest.id.value
            )
            .values(related_evidence_id=first_tenant.latest.id.value)
        )


def test_concurrent_correction_and_revocation_leave_one_valid_history(engine: Engine) -> None:
    actor = _seed_collecting(engine, owner=True)
    service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    registered = service.register(actor, _register_command(engine, actor)).history
    correction = CorrectEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=registered.latest.id,
        expected_evidence_digest=registered.latest.evidence_digest,
        kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/legal_name", response_sha256=sha256(ORIGINAL).hexdigest()
        ),
        located_content=b"Empresa Exemplo Ltda.",
        content_original="Empresa Exemplo Ltda.",
        extraction_method="HUMAN_CORRECTION",
        extraction_method_version="1.0.0",
    )
    revocation = RevokeEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=registered.latest.id,
        expected_evidence_digest=registered.latest.evidence_digest,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
    )
    barrier = Barrier(2)

    def correct() -> str:
        barrier.wait()
        try:
            EvidenceService(
                PostgreSQLUnitOfWorkFactory(engine),
                ContextualAuthorizer(),
                FakeClock(NOW),
            ).correct(actor, correction)
        except EvidenceAlreadyRevokedError, EvidenceVersionConflictError:
            return "conflict"
        return "success"

    def revoke() -> str:
        barrier.wait()
        try:
            EvidenceService(
                PostgreSQLUnitOfWorkFactory(engine),
                ContextualAuthorizer(),
                FakeClock(NOW),
            ).revoke(actor, revocation)
        except EvidenceAlreadyRevokedError, EvidenceVersionConflictError:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(correct), executor.submit(revoke)]
        outcomes = [future.result(timeout=20) for future in futures]

    assert sorted(outcomes) == ["conflict", "success"]
    history = service.get_history(actor, registered.latest.id)
    assert (len(history.versions), history.is_revoked) in {(1, True), (2, False)}


def test_f51_migration_matches_metadata_and_refuses_destructive_downgrade(
    engine: Engine,
) -> None:
    inspector = sa.inspect(engine)
    assert {"evidence_artifact", "evidence", "evidence_lifecycle_event"} <= set(
        inspector.get_table_names()
    )
    assert {constraint["name"] for constraint in inspector.get_foreign_keys("evidence")} >= {
        "fk_evidence_artifact_scope",
        "fk_evidence_company_scope",
        "fk_evidence_decision_scope",
        "fk_evidence_investigation_scope",
        "fk_evidence_series_scope",
        "fk_evidence_supersedes_scope",
    }
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    alembic_command.check(config)

    actor = _seed_collecting(engine)
    EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).register(actor, _register_command(engine, actor))
    with pytest.raises(RuntimeError, match=r"Cannot downgrade F5\.1"):
        alembic_command.downgrade(config, "20260811_10")
