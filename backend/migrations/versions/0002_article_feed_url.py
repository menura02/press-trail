"""Scope feed identifiers to the address that supplied them."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("articles", sa.Column("feed_url", sa.String(), nullable=True))
    op.execute("""
        UPDATE articles
        SET feed_url = (SELECT url FROM sources WHERE sources.id = articles.source_id)
        WHERE feed_id IS NOT NULL
    """)


def downgrade():
    op.drop_column("articles", "feed_url")

