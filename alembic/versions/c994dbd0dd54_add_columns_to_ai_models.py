# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

"""Add columns to ai models

Revision ID: c994dbd0dd54
Revises: 20fb10f0cbf3
Create Date: 2025-04-15 14:19:28.305762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c994dbd0dd54'
down_revision: Union[str, None] = '20fb10f0cbf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add new columns
    op.add_column('ai_models', sa.Column('token_rate', sa.Float(), nullable=True))
    op.add_column('ai_models', sa.Column('input_price', sa.Float(), nullable=True))
    op.add_column('ai_models', sa.Column('output_price', sa.Float(), nullable=True))

    # Update existing records based on identifier
    BEDROCK_MODELS = {
        'amazon.nova-micro-v1:0': {'token_rate': 5.5, 'input_price': 0.000046, 'output_price': 0.000184},
        'amazon.nova-lite-v1:0': {'token_rate': 5.5, 'input_price': 0.000078, 'output_price': 0.000312},
        'amazon.nova-pro-v1:0': {'token_rate': 5.5, 'input_price': 0.00105, 'output_price': 0.0042},
        'anthropic.claude-3-5-sonnet-20240620-v1:0': {'token_rate': 6, 'input_price': 0.003, 'output_price': 0.015},
        'anthropic.claude-3-sonnet-20240229-v1:0': {'token_rate': 6, 'input_price': 0.003, 'output_price': 0.015},
        'anthropic.claude-v2': {'token_rate': 6, 'input_price': 0.008, 'output_price': 0.024},
        'anthropic.claude-instant-v1': {'token_rate': 6, 'input_price': 0.0008, 'output_price': 0.0024},
        'meta.llama3-2-1b-instruct-v1:0': {'token_rate': 4, 'input_price': 0.00013, 'output_price': 0.00013},
        'meta.llama3-2-3b-instruct-v1:0': {'token_rate': 4, 'input_price': 0.00019, 'output_price': 0.00019},
    }
    
    conn = op.get_bind()
    for identifier, values in BEDROCK_MODELS.items():
        conn.execute(
            sa.text("""
                UPDATE ai_models 
                SET token_rate = :token_rate, input_price = :input_price, output_price = :output_price 
                WHERE identifier = :identifier
            """),
            {
                'token_rate': values['token_rate'],
                'input_price': values['input_price'],
                'output_price': values['output_price'],
                'identifier': identifier
            }
        )


def downgrade():
    op.drop_column("ai_models", "token_rate")
    op.drop_column("ai_models", "input_price")
    op.drop_column("ai_models", "output_price")