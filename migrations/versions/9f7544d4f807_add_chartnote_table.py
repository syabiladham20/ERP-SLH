"""add chartnote table

Revision ID: 9f7544d4f807
Revises: 6ff6cc56be4f
Create Date: 2026-04-27 09:57:37.273783

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f7544d4f807'
down_revision = '6ff6cc56be4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('chart_note',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flock_id', sa.Integer(), nullable=False),
    sa.Column('chart_identifier', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('pos_x', sa.Float(), nullable=False),
    sa.Column('pos_y', sa.Float(), nullable=False),
    sa.Column('width', sa.Float(), nullable=False),
    sa.Column('height', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.ForeignKeyConstraint(['flock_id'], ['flock.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chart_note_chart_identifier'), 'chart_note', ['chart_identifier'], unique=False)
    op.create_index(op.f('ix_chart_note_flock_id'), 'chart_note', ['flock_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_chart_note_flock_id'), table_name='chart_note')
    op.drop_index(op.f('ix_chart_note_chart_identifier'), table_name='chart_note')
    op.drop_table('chart_note')
