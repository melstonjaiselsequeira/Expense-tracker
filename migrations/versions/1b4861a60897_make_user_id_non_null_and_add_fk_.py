"""Add user_id column with FK, backfill admin, and make non-null.

Revision ID: 1b4861a60897
Revises: 
Create Date: 2026-10-27 18:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import datetime

# revision identifiers, used by Alembic.
revision = '1b4861a60897'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Ensure no leftover temp table from previous failed migration
    op.execute('DROP TABLE IF EXISTS _alembic_tmp_expenses')
    # Add user_id column (nullable) and foreign key
    with op.batch_alter_table('expenses') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_expenses_user', 'users', ['user_id'], ['id'])
    # Insert admin user with known password hash if not exists
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        op.execute(
            "INSERT OR IGNORE INTO users (full_name, email, password_hash, is_verified, created_at, is_active) "
            "VALUES ('Admin', 'admin@example.com', 'pbkdf2:sha256:1000000$ZQ3SFK5EQjOEyZgB$bd08c8e4455f5b4c57dda70a71eae124c1f1296d4f943c49a059705ddde0b2d1', 1, datetime('now'), 1)"
        )
    else:
        # PostgreSQL / MySQL compatible
        op.execute(
            "INSERT INTO users (full_name, email, password_hash, is_verified, created_at, is_active) "
            "VALUES ('Admin', 'admin@example.com', 'pbkdf2:sha256:1000000$ZQ3SFK5EQjOEyZgB$bd08c8e4455f5b4c57dda70a71eae124c1f1296d4f943c49a059705ddde0b2d1', true, NOW(), true) "
            "ON CONFLICT (email) DO NOTHING"
        )
    # Backfill existing expenses with admin user_id
    conn = op.get_bind()
    admin_id = conn.execute(text("SELECT id FROM users WHERE email='admin@example.com'")).scalar()
    if admin_id is not None:
        conn.execute(text("UPDATE expenses SET user_id = :admin_id WHERE user_id IS NULL").bindparams(admin_id=admin_id))
    # Make user_id non-null
    with op.batch_alter_table('expenses') as batch_op:
        batch_op.alter_column('user_id', nullable=False)

def downgrade():
    # Revert user_id column changes
    with op.batch_alter_table('expenses') as batch_op:
        batch_op.alter_column('user_id', nullable=True)
        batch_op.drop_constraint('fk_expenses_user', type_='foreignkey')
        batch_op.drop_column('user_id')
