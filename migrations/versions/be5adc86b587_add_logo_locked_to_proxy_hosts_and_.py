"""add logo_locked to proxy_hosts and guests

Revision ID: be5adc86b587
Revises: 32a2dadd26d2
Create Date: 2026-08-23 23:47:57.857044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be5adc86b587'
down_revision: Union[str, None] = '32a2dadd26d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows get a value - the model's Python-side default only applies
    # to new rows the ORM inserts, not rows that already exist in the DB (same reasoning as
    # dashboards.tile_size's migration).
    op.add_column(
        'proxy_hosts', sa.Column('logo_locked', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        'guests', sa.Column('logo_locked', sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column('guests', 'logo_locked')
    op.drop_column('proxy_hosts', 'logo_locked')
