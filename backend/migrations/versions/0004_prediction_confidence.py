"""预测把握程度：predictions.confidence、attempts.confidence（1 没把握 / 2 有点把握 / 3 很有把握）

Revision ID: 0004_confidence
Revises: 45b858cf6355
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004_confidence'
down_revision: Union[str, None] = '45b858cf6355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('predictions') as batch:
        batch.add_column(sa.Column('confidence', sa.Integer(), nullable=True))
    with op.batch_alter_table('attempts') as batch:
        batch.add_column(sa.Column('confidence', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('attempts') as batch:
        batch.drop_column('confidence')
    with op.batch_alter_table('predictions') as batch:
        batch.drop_column('confidence')
