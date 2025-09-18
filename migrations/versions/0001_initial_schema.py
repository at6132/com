"""Initial database schema

Revision ID: 0001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create orders table
    op.create_table('orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_ref', sa.String(length=50), nullable=False),
        sa.Column('strategy_id', sa.String(length=100), nullable=False),
        sa.Column('instance_id', sa.String(length=100), nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('instrument_class', sa.String(length=20), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('order_type', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('stop_price', sa.Float(), nullable=True),
        sa.Column('time_in_force', sa.String(length=10), nullable=False),
        sa.Column('expire_at', sa.DateTime(), nullable=True),
        sa.Column('post_only', sa.Boolean(), nullable=True),
        sa.Column('reduce_only', sa.Boolean(), nullable=True),
        sa.Column('hidden', sa.Boolean(), nullable=True),
        sa.Column('allow_partial_fills', sa.Boolean(), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=True),
        sa.Column('broker_order_id', sa.String(length=100), nullable=True),
        sa.Column('venue', sa.String(length=50), nullable=True),
        sa.Column('risk_config', sa.Text(), nullable=True),
        sa.Column('routing_config', sa.Text(), nullable=True),
        sa.Column('leverage_config', sa.Text(), nullable=True),
        sa.Column('exit_plan', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('position_ref', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_ref')
    )
    op.create_index('idx_orders_strategy_symbol_state', 'orders', ['strategy_id', 'symbol', 'state'], unique=False)
    op.create_index('idx_orders_strategy_created', 'orders', ['strategy_id', 'created_at'], unique=False)
    op.create_index('idx_orders_broker_order', 'orders', ['broker', 'broker_order_id'], unique=False)

    # Create positions table
    op.create_table('positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_ref', sa.String(length=50), nullable=False),
        sa.Column('strategy_id', sa.String(length=100), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('avg_entry', sa.Float(), nullable=True),
        sa.Column('net_qty', sa.Float(), nullable=True),
        sa.Column('net_notional', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('leverage_config', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('position_ref')
    )
    op.create_index('idx_positions_strategy_symbol', 'positions', ['strategy_id', 'symbol'], unique=False)
    op.create_index('idx_positions_strategy_state', 'positions', ['strategy_id', 'state'], unique=False)

    # Create suborders table
    op.create_table('suborders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sub_order_ref', sa.String(length=50), nullable=False),
        sa.Column('position_ref', sa.String(length=50), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('allocation', sa.Text(), nullable=False),
        sa.Column('trigger', sa.Text(), nullable=False),
        sa.Column('exec_config', sa.Text(), nullable=False),
        sa.Column('after_fill_actions', sa.Text(), nullable=True),
        sa.Column('broker_order_id', sa.String(length=100), nullable=True),
        sa.Column('filled_qty', sa.Float(), nullable=True),
        sa.Column('remaining_qty', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['position_ref'], ['positions.position_ref'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sub_order_ref')
    )
    op.create_index('idx_suborders_position_state', 'suborders', ['position_ref', 'state'], unique=False)
    op.create_index('idx_suborders_broker_order', 'suborders', ['broker_order_id'], unique=False)

    # Create fills table
    op.create_table('fills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fill_id', sa.String(length=100), nullable=False),
        sa.Column('order_ref', sa.String(length=50), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('liquidity', sa.String(length=10), nullable=False),
        sa.Column('fee_amount', sa.Float(), nullable=True),
        sa.Column('fee_currency', sa.String(length=10), nullable=True),
        sa.Column('filled_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_ref'], ['orders.order_ref'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fill_id')
    )
    op.create_index('idx_fills_order_ref', 'fills', ['order_ref'], unique=False)
    op.create_index('idx_fills_filled_at', 'fills', ['filled_at'], unique=False)

    # Create events table
    op.create_table('events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('order_ref', sa.String(length=50), nullable=False),
        sa.Column('position_ref', sa.String(length=50), nullable=True),
        sa.Column('sub_order_ref', sa.String(length=50), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_ref'], ['orders.order_ref'], ),
        sa.ForeignKeyConstraint(['position_ref'], ['positions.position_ref'], ),
        sa.ForeignKeyConstraint(['sub_order_ref'], ['suborders.sub_order_ref'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id')
    )
    op.create_index('idx_events_type_occurred', 'events', ['event_type', 'occurred_at'], unique=False)
    op.create_index('idx_events_order_ref', 'events', ['order_ref'], unique=False)
    op.create_index('idx_events_strategy_occurred', 'events', ['occurred_at'], unique=False)

    # Create idempotency_records table
    op.create_table('idempotency_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('request_type', sa.String(length=50), nullable=False),
        sa.Column('result_ref', sa.String(length=50), nullable=False),
        sa.Column('result_data', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('idx_idempotency_expires', 'idempotency_records', ['expires_at'], unique=False)
    op.create_index('idx_idempotency_request_type', 'idempotency_records', ['request_type'], unique=False)

    # Create api_keys table
    op.create_table('api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('permissions', sa.Text(), nullable=False),
        sa.Column('secret_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('rate_limit_per_hour', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_id')
    )
    op.create_index('idx_api_keys_owner', 'api_keys', ['owner'], unique=False)
    op.create_index('idx_api_keys_active', 'api_keys', ['is_active'], unique=False)

    # Note: Foreign key constraints removed for SQLite compatibility
    # The position_ref column exists but without formal foreign key constraint


def downgrade() -> None:
    # Note: No foreign key constraints to remove
    
    # Drop tables in reverse order
    op.drop_table('api_keys')
    op.drop_table('idempotency_records')
    op.drop_table('events')
    op.drop_table('fills')
    op.drop_table('suborders')
    op.drop_table('positions')
    op.drop_table('orders')
