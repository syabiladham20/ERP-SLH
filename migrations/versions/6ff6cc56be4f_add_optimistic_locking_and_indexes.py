"""Add optimistic locking and indexes

Revision ID: 6ff6cc56be4f
Revises: 3aab2d252ffe
Create Date: 2026-04-27 07:44:04.204647

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ff6cc56be4f'
down_revision = '3aab2d252ffe'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('clinical_note', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_clinical_note_log_id'), ['log_id'], unique=False)

    with op.batch_alter_table('daily_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_daily_log_feed_code_female_id'), ['feed_code_female_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_daily_log_feed_code_male_id'), ['feed_code_male_id'], unique=False)

    with op.batch_alter_table('daily_log_photo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_daily_log_photo_note_id'), ['note_id'], unique=False)

    with op.batch_alter_table('floating_note', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_floating_note_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_floating_note_flock_id'), ['flock_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_floating_note_x_value'), ['x_value'], unique=False)

    with op.batch_alter_table('flock_grading', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_flock_grading_age_week'), ['age_week'], unique=False)
        batch_op.create_index(batch_op.f('ix_flock_grading_house_id'), ['house_id'], unique=False)

    with op.batch_alter_table('hatchability', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_hatchability_candling_date'), ['candling_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_hatchability_flock_id'), ['flock_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_hatchability_hatching_date'), ['hatching_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_hatchability_setting_date'), ['setting_date'], unique=False)

    with op.batch_alter_table('inventory_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))

    with op.batch_alter_table('inventory_transaction', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_inventory_transaction_inventory_item_id'), ['inventory_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inventory_transaction_transaction_date'), ['transaction_date'], unique=False)

    with op.batch_alter_table('medication', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_medication_end_date'), ['end_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_medication_flock_id'), ['flock_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medication_inventory_item_id'), ['inventory_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medication_start_date'), ['start_date'], unique=False)

    with op.batch_alter_table('partition_weight', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_partition_weight_log_id'), ['log_id'], unique=False)

    with op.batch_alter_table('sampling_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_sampling_event_age_week'), ['age_week'], unique=False)
        batch_op.create_index(batch_op.f('ix_sampling_event_flock_id'), ['flock_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sampling_event_status'), ['status'], unique=False)

    with op.batch_alter_table('vaccine', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_vaccine_actual_date'), ['actual_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_vaccine_est_date'), ['est_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_vaccine_flock_id'), ['flock_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_vaccine_inventory_item_id'), ['inventory_item_id'], unique=False)


def downgrade():
    with op.batch_alter_table('vaccine', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vaccine_inventory_item_id'))
        batch_op.drop_index(batch_op.f('ix_vaccine_flock_id'))
        batch_op.drop_index(batch_op.f('ix_vaccine_est_date'))
        batch_op.drop_index(batch_op.f('ix_vaccine_actual_date'))
        batch_op.drop_column('version')

    with op.batch_alter_table('sampling_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sampling_event_status'))
        batch_op.drop_index(batch_op.f('ix_sampling_event_flock_id'))
        batch_op.drop_index(batch_op.f('ix_sampling_event_age_week'))
        batch_op.drop_column('version')

    with op.batch_alter_table('partition_weight', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_partition_weight_log_id'))
        batch_op.drop_column('version')

    with op.batch_alter_table('medication', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_medication_start_date'))
        batch_op.drop_index(batch_op.f('ix_medication_inventory_item_id'))
        batch_op.drop_index(batch_op.f('ix_medication_flock_id'))
        batch_op.drop_index(batch_op.f('ix_medication_end_date'))
        batch_op.drop_column('version')

    with op.batch_alter_table('inventory_transaction', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventory_transaction_transaction_date'))
        batch_op.drop_index(batch_op.f('ix_inventory_transaction_inventory_item_id'))
        batch_op.drop_column('version')

    with op.batch_alter_table('inventory_item', schema=None) as batch_op:
        batch_op.drop_column('version')

    with op.batch_alter_table('hatchability', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_hatchability_setting_date'))
        batch_op.drop_index(batch_op.f('ix_hatchability_hatching_date'))
        batch_op.drop_index(batch_op.f('ix_hatchability_flock_id'))
        batch_op.drop_index(batch_op.f('ix_hatchability_candling_date'))
        batch_op.drop_column('version')

    with op.batch_alter_table('flock_grading', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_flock_grading_house_id'))
        batch_op.drop_index(batch_op.f('ix_flock_grading_age_week'))
        batch_op.drop_column('version')

    with op.batch_alter_table('floating_note', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_floating_note_x_value'))
        batch_op.drop_index(batch_op.f('ix_floating_note_flock_id'))
        batch_op.drop_index(batch_op.f('ix_floating_note_created_at'))
        batch_op.drop_column('version')

    with op.batch_alter_table('daily_log_photo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_log_photo_note_id'))
        batch_op.drop_column('version')

    with op.batch_alter_table('daily_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_log_feed_code_male_id'))
        batch_op.drop_index(batch_op.f('ix_daily_log_feed_code_female_id'))
        batch_op.drop_column('version')

    with op.batch_alter_table('clinical_note', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clinical_note_log_id'))
        batch_op.drop_column('version')
