"""add_broiler_models

Revision ID: 321a423db419
Revises: 9f7544d4f807
Create Date: 2026-04-28 05:03:45.903038

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '321a423db419'
down_revision = '9f7544d4f807'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('broiler_flock',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('farm_name', sa.String(length=100), nullable=True),
    sa.Column('house_name', sa.String(length=100), nullable=True),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('breed', sa.String(length=50), nullable=True),
    sa.Column('intake_birds', sa.Integer(), nullable=False),
    sa.Column('intake_date', sa.Date(), nullable=False),
    sa.Column('arrival_weight_g', sa.Float(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('broiler_daily_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flock_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('day_number', sa.Integer(), nullable=False),
    sa.Column('death_count', sa.Integer(), nullable=True),
    sa.Column('feed_receive', sa.String(length=100), nullable=True),
    sa.Column('feed_type', sa.String(length=100), nullable=True),
    sa.Column('feed_daily_use_kg', sa.Float(), nullable=True),
    sa.Column('body_weight_g', sa.Float(), nullable=True),
    sa.Column('standard_fcr', sa.Float(), nullable=True),
    sa.Column('medication_vaccine', sa.String(length=200), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['flock_id'], ['broiler_flock.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('broiler_daily_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_broiler_daily_log_date'), ['date'], unique=False)
        batch_op.create_index(batch_op.f('ix_broiler_daily_log_flock_id'), ['flock_id'], unique=False)


def downgrade():
    with op.batch_alter_table('broiler_daily_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_broiler_daily_log_flock_id'))
        batch_op.drop_index(batch_op.f('ix_broiler_daily_log_date'))

    op.drop_table('broiler_daily_log')
    op.drop_table('broiler_flock')
