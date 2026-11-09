"""initial schema"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('clusters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clusters_created_at'), 'clusters', ['created_at'], unique=False)
    op.create_table('sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('full_text', sa.Boolean(), nullable=False),
    sa.Column('interval_minutes', sa.Integer(), nullable=False),
    sa.Column('next_check', sa.DateTime(timezone=True), nullable=False),
    sa.Column('etag', sa.String(), nullable=True),
    sa.Column('modified', sa.String(), nullable=True),
    sa.Column('demo', sa.Boolean(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_sources_next_check'), 'sources', ['next_check'], unique=False)
    op.create_table('articles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('feed_id', sa.String(), nullable=True),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'url')
    )
    op.create_index('ix_article_feed_id', 'articles', ['source_id', 'feed_id'], unique=False)
    op.create_table('fetch_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token', sa.String(length=32), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('seen', sa.Integer(), nullable=False),
    sa.Column('versions', sa.Integer(), nullable=False),
    sa.Column('skipped', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fetch_runs_source_id'), 'fetch_runs', ['source_id'], unique=False)
    op.create_index('ix_run_claim', 'fetch_runs', ['status', 'available_at', 'lease_until'], unique=False)
    op.create_index('uq_source_pending', 'fetch_runs', ['source_id'], unique=True, postgresql_where=sa.text("status IN ('queued','running')"), sqlite_where=sa.text("status IN ('queued','running')"))
    op.create_table('article_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('summary', sa.String(), nullable=False),
    sa.Column('body', sa.String(), nullable=False),
    sa.Column('digest', sa.String(), nullable=False),
    sa.Column('fingerprint', sa.String(), nullable=False),
    sa.Column('published', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated', sa.DateTime(timezone=True), nullable=True),
    sa.Column('published_raw', sa.String(), nullable=True),
    sa.Column('updated_raw', sa.String(), nullable=True),
    sa.Column('published_state', sa.String(), nullable=False),
    sa.Column('updated_state', sa.String(), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('scope', sa.String(), nullable=False),
    sa.Column('extractor', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_versions_article_id'), 'article_versions', ['article_id'], unique=False)
    op.create_table('cluster_members',
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('cluster_id', sa.Integer(), nullable=True),
    sa.Column('decision', sa.String(), nullable=False),
    sa.Column('method', sa.String(), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
    sa.ForeignKeyConstraint(['cluster_id'], ['clusters.id'], ),
    sa.PrimaryKeyConstraint('article_id')
    )
    op.create_index(op.f('ix_cluster_members_cluster_id'), 'cluster_members', ['cluster_id'], unique=False)
    op.create_table('article_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('context', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['version_id'], ['article_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_links_url'), 'article_links', ['url'], unique=False)
    op.create_index(op.f('ix_article_links_version_id'), 'article_links', ['version_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_article_links_version_id'), table_name='article_links')
    op.drop_index(op.f('ix_article_links_url'), table_name='article_links')
    op.drop_table('article_links')
    op.drop_index(op.f('ix_cluster_members_cluster_id'), table_name='cluster_members')
    op.drop_table('cluster_members')
    op.drop_index(op.f('ix_article_versions_article_id'), table_name='article_versions')
    op.drop_table('article_versions')
    op.drop_index('uq_source_pending', table_name='fetch_runs', postgresql_where=sa.text("status IN ('queued','running')"), sqlite_where=sa.text("status IN ('queued','running')"))
    op.drop_index('ix_run_claim', table_name='fetch_runs')
    op.drop_index(op.f('ix_fetch_runs_source_id'), table_name='fetch_runs')
    op.drop_table('fetch_runs')
    op.drop_index('ix_article_feed_id', table_name='articles')
    op.drop_table('articles')
    op.drop_index(op.f('ix_sources_next_check'), table_name='sources')
    op.drop_table('sources')
    op.drop_index(op.f('ix_clusters_created_at'), table_name='clusters')
    op.drop_table('clusters')


