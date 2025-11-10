# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""Add LTI platforms

Revision ID: 5266bb36fb1e
Revises: 7bc0fa4eebdb
Create Date: 2025-06-04 17:04:34.960340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5266bb36fb1e'
down_revision: Union[str, None] = '7bc0fa4eebdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SERVER_DEFAULT_NOW = sa.text('now()')

def upgrade() -> None:
    # Create LTI platforms table
    op.create_table('lti_platforms',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('issuer', sa.String(), nullable=False),
        sa.Column('platform_type', sa.String(), nullable=True),  # e.g., 'moodle', 'canvas', 'blackboard', etc.
        sa.Column('auth_login_url', sa.String(), nullable=False),
        sa.Column('auth_token_url', sa.String(), nullable=False),
        sa.Column('key_set_url', sa.String(), nullable=False),
        sa.Column('deployment_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('custom_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=SERVER_DEFAULT_NOW, nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=SERVER_DEFAULT_NOW, onupdate=SERVER_DEFAULT_NOW, nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lti_platforms_id'), 'lti_platforms', ['id'], unique=False)
    op.create_index(op.f('ix_lti_platforms_client_id'), 'lti_platforms', ['client_id'], unique=False)
    
    # Update groups table to add lti_private_key column
    op.add_column('groups', sa.Column('lti_private_key', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    # Drop LTI platforms table
    op.drop_index(op.f('ix_lti_platforms_client_id'), table_name='lti_platforms')
    op.drop_index(op.f('ix_lti_platforms_id'), table_name='lti_platforms')
    op.drop_table('lti_platforms')

    # Drop lti_private_key column from groups table
    op.drop_column('groups', 'lti_private_key')
