"""normalize enum values to lowercase

Revision ID: f17252149087
Revises: f2fde163c850
Create Date: 2026-09-07 11:07:37.939600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f17252149087'
down_revision: Union[str, Sequence[str], None] = 'f2fde163c850'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Original enum values were stored using Python enum member names
    # (uppercase) rather than their .value attribute (lowercase), while
    # the 'admin'/'none' values added in the previous migration were
    # already lowercase. This normalizes everything to lowercase, matching
    # shared/enums.py's actual .value strings used throughout the codebase.
    op.execute("ALTER TYPE userrole RENAME VALUE 'EMPLOYEE' TO 'employee'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'COMPLIANCE' TO 'compliance'")

    op.execute("ALTER TYPE sessionrole RENAME VALUE 'CUSTOMER' TO 'customer'")
    op.execute("ALTER TYPE sessionrole RENAME VALUE 'EMPLOYEE' TO 'employee'")
    op.execute("ALTER TYPE sessionrole RENAME VALUE 'COMPLIANCE' TO 'compliance'")

    op.execute("ALTER TYPE accesslevel RENAME VALUE 'PUBLIC' TO 'public'")
    op.execute("ALTER TYPE accesslevel RENAME VALUE 'INTERNAL' TO 'internal'")
    op.execute("ALTER TYPE accesslevel RENAME VALUE 'RESTRICTED' TO 'restricted'")


def downgrade() -> None:
    op.execute("ALTER TYPE userrole RENAME VALUE 'employee' TO 'EMPLOYEE'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'compliance' TO 'COMPLIANCE'")

    op.execute("ALTER TYPE sessionrole RENAME VALUE 'customer' TO 'CUSTOMER'")
    op.execute("ALTER TYPE sessionrole RENAME VALUE 'employee' TO 'EMPLOYEE'")
    op.execute("ALTER TYPE sessionrole RENAME VALUE 'compliance' TO 'COMPLIANCE'")

    op.execute("ALTER TYPE accesslevel RENAME VALUE 'public' TO 'PUBLIC'")
    op.execute("ALTER TYPE accesslevel RENAME VALUE 'internal' TO 'INTERNAL'")
    op.execute("ALTER TYPE accesslevel RENAME VALUE 'restricted' TO 'RESTRICTED'")