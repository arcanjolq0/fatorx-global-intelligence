"""Harden F4.4 plan continuity audit cost metadata.

Revision ID: 20260801_07
Revises: 20260801_06
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260801_07"
down_revision: str | None = "20260801_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_audit_event_investigation_planning_cost_consistency"
_F441_COST_CONSISTENCY = (
    "(planning_command_id IS NULL "
    "AND planning_maximum_estimated_cost_kind IS NULL "
    "AND planning_maximum_estimated_cost_amount IS NULL "
    "AND planning_maximum_estimated_cost_currency IS NULL) OR "
    "(planning_command_id IS NOT NULL "
    "AND planning_maximum_estimated_cost_kind IS NOT NULL AND "
    "((planning_maximum_estimated_cost_kind = 'UNKNOWN' "
    "AND planning_maximum_estimated_cost_amount IS NULL "
    "AND planning_maximum_estimated_cost_currency IS NULL) OR "
    "(planning_maximum_estimated_cost_kind = 'KNOWN' "
    "AND planning_maximum_estimated_cost_amount IS NOT NULL "
    "AND planning_maximum_estimated_cost_currency IS NOT NULL)))"
)
_F44_COST_CONSISTENCY = (
    "(planning_maximum_estimated_cost_amount IS NULL) = "
    "(planning_maximum_estimated_cost_currency IS NULL) AND "
    "(planning_maximum_estimated_cost_kind = 'KNOWN') = "
    "(planning_maximum_estimated_cost_amount IS NOT NULL)"
)


def upgrade() -> None:
    """Reject orphan or partial F4.4 planning-cost audit metadata."""

    op.drop_constraint(op.f(_CONSTRAINT_NAME), "audit_event", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "audit_event",
        _F441_COST_CONSISTENCY,
    )


def downgrade() -> None:
    """Restore the original F4.4 cost-pair constraint."""

    op.drop_constraint(op.f(_CONSTRAINT_NAME), "audit_event", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "audit_event",
        _F44_COST_CONSISTENCY,
    )
