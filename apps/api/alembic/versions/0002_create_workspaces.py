"""create workspaces tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13

Workspaces persistence layer (ADR-0018): workspaces -> json_documents ->
json_versions. Composite UNIQUE constraints double as the query/cascade
indexes (each leads with the FK column), so no separate FK indexes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_workspaces_user_name"),
    )
    # At most one default workspace per user; partial unique index keyed on
    # is_default (not name) keeps provisioning idempotent after renames.
    op.create_index(
        "uq_workspaces_user_default",
        "workspaces",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "json_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(length=100), nullable=False),
        # Historical high-water mark for version numbers: deleting the top
        # version must not let its number be reused (requirements DB-06).
        sa.Column(
            "last_version_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "tag", name="uq_json_documents_ws_tag"),
    )

    op.create_table(
        "json_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("json_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_json_versions_doc_number"
        ),
    )


def downgrade() -> None:
    op.drop_table("json_versions")
    op.drop_table("json_documents")
    op.drop_index("uq_workspaces_user_default", table_name="workspaces")
    op.drop_table("workspaces")
