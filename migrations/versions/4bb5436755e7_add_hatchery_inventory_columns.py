"""add hatchery inventory columns

Revision ID: 4bb5436755e7
Revises: 321a423db419
Create Date: 2024-05-02 08:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bb5436755e7'
down_revision = '321a423db419'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inventory_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('unit_of_measurement', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('location', sa.String(length=50), server_default='Farm'))

    with op.batch_alter_table('inventory_transaction', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location', sa.String(length=50), server_default='Farm'))
        batch_op.add_column(sa.Column('classification', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('inventory_transaction', schema=None) as batch_op:
        batch_op.drop_column('classification')
        batch_op.drop_column('location')

    with op.batch_alter_table('inventory_item', schema=None) as batch_op:
        batch_op.drop_column('location')
        batch_op.drop_column('unit_of_measurement')
        batch_op.drop_column('category')
