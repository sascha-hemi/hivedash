"""add custom services and global service identity

Revision ID: 32a2dadd26d2
Revises: 7374598b6c37
Create Date: 2026-08-23 22:32:34.357486

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32a2dadd26d2'
down_revision: Union[str, None] = '7374598b6c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # global identity fields on the two auto-discovered service tables - same idiom as logo_id
    # ("what this service is", not per-dashboard).
    op.add_column('proxy_hosts', sa.Column('custom_name', sa.String(), nullable=True))
    op.add_column('proxy_hosts', sa.Column('custom_url', sa.String(), nullable=True))
    op.add_column('guests', sa.Column('custom_name', sa.String(), nullable=True))
    op.add_column('guests', sa.Column('custom_url', sa.String(), nullable=True))

    # best-effort carry-forward: fold any values already set via the (now-removed) per-dashboard
    # dashboard_items.display_name_override/custom_url onto the corresponding service's new global
    # column, so the "Dienste" page starts populated rather than silently losing what an admin
    # already configured. If the same service had conflicting overrides on multiple dashboards,
    # the last one processed wins - acceptable for this app's current single-default-dashboard
    # reality, not worth a more elaborate merge.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT proxy_host_id, guest_id, display_name_override, custom_url FROM dashboard_items "
        "WHERE display_name_override IS NOT NULL OR custom_url IS NOT NULL"
    )).fetchall()
    for proxy_host_id, guest_id, name, url in rows:
        if proxy_host_id is not None:
            conn.execute(
                sa.text(
                    "UPDATE proxy_hosts SET custom_name = COALESCE(:name, custom_name), "
                    "custom_url = COALESCE(:url, custom_url) WHERE id = :id"
                ),
                {"name": name, "url": url, "id": proxy_host_id},
            )
        elif guest_id is not None:
            conn.execute(
                sa.text(
                    "UPDATE guests SET custom_name = COALESCE(:name, custom_name), "
                    "custom_url = COALESCE(:url, custom_url) WHERE id = :id"
                ),
                {"name": name, "url": url, "id": guest_id},
            )

    # wholly admin-created services with no NPM/Proxmox counterpart at all.
    op.create_table(
        'custom_services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('logo_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['logo_id'], ['logos.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # dashboard_items: add the third possible target, widen the "exactly one" check constraint to
    # cover it, and drop the two per-dashboard override columns now superseded by the global
    # columns above. SQLite has no ALTER for constraints or column drops - needs batch/recreate.
    with op.batch_alter_table('dashboard_items', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('custom_service_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_dashboard_items_custom_service_id_custom_services', 'custom_services',
            ['custom_service_id'], ['id'], ondelete='CASCADE',
        )
        batch_op.create_unique_constraint(
            'uq_dashboard_item_custom_service', ['dashboard_id', 'custom_service_id']
        )
        batch_op.drop_constraint('ck_dashboard_item_exactly_one_target', type_='check')
        batch_op.create_check_constraint(
            'ck_dashboard_item_exactly_one_target',
            "(CASE WHEN proxy_host_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN guest_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN custom_service_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        )
        batch_op.drop_column('display_name_override')
        batch_op.drop_column('custom_url')


def downgrade() -> None:
    with op.batch_alter_table('dashboard_items', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('display_name_override', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('custom_url', sa.String(), nullable=True))
        batch_op.drop_constraint('ck_dashboard_item_exactly_one_target', type_='check')
        batch_op.create_check_constraint(
            'ck_dashboard_item_exactly_one_target',
            "(proxy_host_id IS NOT NULL AND guest_id IS NULL) OR "
            "(proxy_host_id IS NULL AND guest_id IS NOT NULL)",
        )
        batch_op.drop_constraint('uq_dashboard_item_custom_service', type_='unique')
        batch_op.drop_constraint(
            'fk_dashboard_items_custom_service_id_custom_services', type_='foreignkey'
        )
        batch_op.drop_column('custom_service_id')

    op.drop_table('custom_services')

    op.drop_column('guests', 'custom_url')
    op.drop_column('guests', 'custom_name')
    op.drop_column('proxy_hosts', 'custom_url')
    op.drop_column('proxy_hosts', 'custom_name')
