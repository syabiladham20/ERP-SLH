"""Add ClinicalNote model and note_id to DailyLogPhoto

Revision ID: b191e49bc61d
Revises: 9782a065a3d5
Create Date: 2026-02-25 07:35:25.861795

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'b191e49bc61d'
down_revision = '9782a065a3d5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table('clinical_note'):
        op.create_table('clinical_note',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('log_id', sa.Integer(), nullable=False),
        sa.Column('caption', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['log_id'], ['daily_log.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    columns = [c['name'] for c in inspector.get_columns('daily_log_photo')]
    if 'note_id' not in columns:
        with op.batch_alter_table('daily_log_photo', schema=None) as batch_op:
            batch_op.add_column(sa.Column('note_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_daily_log_photo_note_id', 'clinical_note', ['note_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    with op.batch_alter_table('daily_log_photo', schema=None) as batch_op:
        # Check constraints might be tricky in batch mode for sqlite, but drop_constraint usually ignores if missing?
        # Safe to try drop.
        try:
            batch_op.drop_constraint('fk_daily_log_photo_note_id', type_='foreignkey')
        except:
            pass

        columns = [c['name'] for c in inspector.get_columns('daily_log_photo')]
        if 'note_id' in columns:
            batch_op.drop_column('note_id')

    if inspector.has_table('clinical_note'):
        op.drop_table('clinical_note')
