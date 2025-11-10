# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""add_notifications_table

Revision ID: 3c97fcbec3ae
Revises: 5266bb36fb1e
Create Date: 2025-06-26 11:14:28.257184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3c97fcbec3ae'
down_revision: Union[str, None] = '5266bb36fb1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notifications table
    op.create_table('notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('use_push_notification', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, default=False),
        sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notification_type', sa.String(), nullable=False, default='info'),
        sa.Column('priority', sa.String(), nullable=False, default='normal'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_notifications_id'), 'notifications', ['id'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_id'), table_name='notifications')
    
    # Drop notifications table
    op.drop_table('notifications')
