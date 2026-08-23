"""add dashboard item custom url

Revision ID: 7374598b6c37
Revises: 76f47c7a8689
Create Date: 2026-08-23 19:36:09.289349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7374598b6c37'
down_revision: Union[str, None] = '76f47c7a8689'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # plain nullable column, no FK/constraint - no batch mode needed (unlike category_id/logo_id).
    op.add_column('dashboard_items', sa.Column('custom_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('dashboard_items', 'custom_url')
