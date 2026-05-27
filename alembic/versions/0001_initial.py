"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-27 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False, index=True),
        sa.Column("doi", sa.String(256), nullable=True, index=True),
        sa.Column("pmid", sa.String(32), nullable=True, index=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("authors", sa.Text, nullable=True),
        sa.Column("journal", sa.String(256), nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relevance_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("technical_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(24), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id", name="uq_paper_source_ext"),
    )

    op.create_table(
        "contents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, sa.ForeignKey("papers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),  # carousel, reel, post, infographic, myth_reality
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("hook", sa.Text, nullable=True),
        sa.Column("caption", sa.Text, nullable=False),
        sa.Column("hashtags", sa.Text, nullable=False, server_default=""),
        sa.Column("cta", sa.Text, nullable=True),
        sa.Column("slides_json", sa.JSON, nullable=True),
        sa.Column("reel_script", sa.Text, nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("validation_json", sa.JSON, nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_id", sa.Integer, sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),  # doi, pmid, url
        sa.Column("identifier", sa.String(256), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("verification_message", sa.Text, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "schedule_slots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_id", sa.Integer, sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False, server_default="instagram"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    op.create_table(
        "analytics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_id", sa.Integer, sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("impressions", sa.Integer, nullable=True),
        sa.Column("reach", sa.Integer, nullable=True),
        sa.Column("likes", sa.Integer, nullable=True),
        sa.Column("comments", sa.Integer, nullable=True),
        sa.Column("saves", sa.Integer, nullable=True),
        sa.Column("shares", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analytics")
    op.drop_table("schedule_slots")
    op.drop_table("sources")
    op.drop_table("contents")
    op.drop_table("papers")
