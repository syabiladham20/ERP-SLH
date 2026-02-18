"""Rename batch_id to flock_id

Revision ID: cf4723a1005d
Revises: aacb806d32d7
Create Date: 2026-02-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cf4723a1005d'
down_revision = 'aacb806d32d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('flock', schema=None) as batch_op:
        batch_op.alter_column('batch_id', new_column_name='flock_id')


def downgrade():
    with op.batch_alter_table('flock', schema=None) as batch_op:
        batch_op.alter_column('flock_id', new_column_name='batch_id')
