"""Harden collection activation historical Company and plan continuity.

Revision ID: 20260802_09
Revises: 20260802_08
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_09"
down_revision: str | None = "20260802_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Correlate every F4.5 transition with the exact run Company and plan."""

    op.add_column(
        "investigation_transition",
        sa.Column("collection_company_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "investigation_transition",
        sa.Column("collection_plan_id", postgresql.UUID(as_uuid=True)),
    )
    op.execute(
        "UPDATE investigation_transition AS transition "
        "SET collection_company_id = run.company_id, collection_plan_id = run.plan_id "
        "FROM collection_run AS run "
        "WHERE transition.collection_run_id = run.id "
        "AND transition.workspace_id = run.workspace_id "
        "AND transition.investigation_id = run.investigation_id"
    )
    op.drop_constraint(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_complete"),
        "investigation_transition",
        type_="check",
    )
    op.create_unique_constraint(
        op.f("uq_collection_run_id_workspace_id_investigation_id_company_id_plan_id"),
        "collection_run",
        ["id", "workspace_id", "investigation_id", "company_id", "plan_id"],
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_complete"),
        "investigation_transition",
        "(command_type = 'START_COLLECTION') = (collection_run_id IS NOT NULL) AND "
        "num_nonnulls(collection_run_id, collection_company_id, collection_plan_id, "
        "collection_operation_count, collection_activation_policy_id, "
        "collection_activation_policy_version) IN (0, 6)",
    )
    op.create_foreign_key(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        "collection_run",
        [
            "collection_run_id",
            "workspace_id",
            "investigation_id",
            "collection_company_id",
            "collection_plan_id",
        ],
        ["id", "workspace_id", "investigation_id", "company_id", "plan_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    )


def downgrade() -> None:
    """Restore the F4.5 four-field transition correlation."""

    op.drop_constraint(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_complete"),
        "investigation_transition",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_complete"),
        "investigation_transition",
        "(command_type = 'START_COLLECTION') = (collection_run_id IS NOT NULL) AND "
        "num_nonnulls(collection_run_id, collection_operation_count, "
        "collection_activation_policy_id, collection_activation_policy_version) IN (0, 4)",
    )
    op.create_foreign_key(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        "collection_run",
        ["collection_run_id", "workspace_id", "investigation_id"],
        ["id", "workspace_id", "investigation_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    )
    op.drop_constraint(
        op.f("uq_collection_run_id_workspace_id_investigation_id_company_id_plan_id"),
        "collection_run",
        type_="unique",
    )
    op.drop_column("investigation_transition", "collection_plan_id")
    op.drop_column("investigation_transition", "collection_company_id")
