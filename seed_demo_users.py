# seed_demo_users.py
from agent1_classification.auth import create_user
from shared.enums import UserRole

DEMO_USERS = [
    ("demo_employee", "DemoEmp123!", UserRole.EMPLOYEE),
    ("demo_compliance", "DemoComp123!", UserRole.COMPLIANCE),
    ("demo_admin", "DemoAdmin123!", UserRole.ADMIN),
]

for username, password, role in DEMO_USERS:
    try:
        create_user(username, password, role)
        print(f"Created: {username} ({role.value})")
    except ValueError as e:
        print(f"Skipped {username}: {e}")  # now shows the REAL reason, not an assumption