"""add user locale

Revision ID: 0e7931683f15
Revises: be5adc86b587
Create Date: 2026-08-24 01:36:59.098971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e7931683f15'
down_revision: Union[str, None] = 'be5adc86b587'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('locale', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'locale')
