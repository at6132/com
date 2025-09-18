"""Add secret_key column to api_keys table

Revision ID: 0002
Revises: 0001
Create Date: 2025-08-28 20:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # For SQLite, we need to use batch operations
    with op.batch_alter_table('api_keys') as batch_op:
        # Add secret_key column
        batch_op.add_column(sa.Column('secret_key', sa.String(length=500), nullable=True))
    
    # For existing records, copy secret_hash to secret_key temporarily
    # This will be updated when we populate with real keys
    op.execute("UPDATE api_keys SET secret_key = secret_hash WHERE secret_key IS NULL")
    
    # For SQLite, we can't easily make it NOT NULL after adding, so we'll handle this in the application

def downgrade() -> None:
    # Remove secret_key column
    with op.batch_alter_table('api_keys') as batch_op:
        batch_op.drop_column('secret_key')
