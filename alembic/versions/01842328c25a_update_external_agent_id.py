# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""Update external agent id

Revision ID: 01842328c25a
Revises: 2bf0f0114584
Create Date: 2025-05-12 19:27:15.443905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01842328c25a'
down_revision: Union[str, None] = '2bf0f0114584'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update public.agents
    op.execute("UPDATE public.agents SET alias_id = 'K85DQ6FANJ' WHERE code = 'external_chatbot'")
    # ### end Alembic commands ###


def downgrade() -> None:
    op.execute("UPDATE public.agents SET alias_id = 'BBU5LCCD41' WHERE code = 'external_chatbot'")
    # ### end Alembic commands ###
