"""merge multiple heads

Revision ID: 9d09e209f638
Revises: 4bb5436755e7, 8ae5a4cb256d
Create Date: 2026-05-02 11:36:33.109494

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d09e209f638'
down_revision = ('4bb5436755e7', '8ae5a4cb256d')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
