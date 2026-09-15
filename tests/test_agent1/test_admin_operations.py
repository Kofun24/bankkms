"""
tests/test_agent1/test_admin_operations.py

Tests for admin_operations.py — employee and document management,
gated by require_admin(). Backed by the real PostgreSQL database
(bankkms-dev), with 'test_' prefixed data and automatic cleanup.

Run with: pytest tests/test_agent1/test_admin_operations.py -v
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from agent1_classification.admin_operations import (
    DocumentNotFoundError,
    EmployeeNotFoundError,
    LastAdminError,
    admin_add_document,
    admin_add_employee,
    admin_deactivate_employee,
    admin_list_documents,
    admin_list_employees,
    admin_promote_to_admin,
    admin_demote_from_admin,
    admin_reactivate_employee,
    admin_retire_document,
    admin_change_role,
    
)
from agent1_classification.auth import UnauthorizedRoleError, create_user, login
from database.config import SessionLocal
from database.models import User, UserRole as DBUserRole
from shared.enums import AccessLevel, UserRole


def make_test_username(suffix: str = "") -> str:
    return f"test_{suffix}_{uuid.uuid4().hex[:8]}"


def make_test_doc_id(suffix: str = "") -> str:
    return f"test_doc_{suffix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_test_data():
    yield

    db = SessionLocal()
    try:
        db.execute(text("""
            DELETE FROM sessions
            WHERE session_token LIKE 'test_%'
               OR user_id IN (SELECT id FROM users WHERE username LIKE 'test_%')
        """))
        db.execute(text("DELETE FROM users WHERE username LIKE 'test_%'"))
        db.execute(text("""
            DELETE FROM document_chunks
            WHERE document_id IN (SELECT id FROM documents WHERE doc_id LIKE 'test_doc_%')
        """))
        db.execute(text("DELETE FROM documents WHERE doc_id LIKE 'test_doc_%'"))
        db.commit()
    finally:
        db.close()


def make_admin_session() -> str:
    """Creates a fresh test admin account and returns a logged-in session_id."""
    username = make_test_username("admin")
    create_user(username, "adminpass123", UserRole.ADMIN)
    return login(username, "adminpass123").session_id


def make_employee_session() -> str:
    """Creates a fresh test employee account and returns a logged-in
    session_id — used to confirm non-admins are rejected."""
    username = make_test_username("emp")
    create_user(username, "emppass123", UserRole.EMPLOYEE)
    return login(username, "emppass123").session_id


# ---------- admin_add_employee ----------

def test_admin_can_add_employee():
    admin_session = make_admin_session()
    new_username = make_test_username("newemp")

    admin_add_employee(admin_session, new_username, "password123", UserRole.EMPLOYEE)

    # verify by logging in as the new account
    ctx = login(new_username, "password123")
    assert ctx.user_role == UserRole.EMPLOYEE


def test_admin_can_add_compliance_officer():
    admin_session = make_admin_session()
    new_username = make_test_username("newcomp")

    admin_add_employee(admin_session, new_username, "password123", UserRole.COMPLIANCE)

    ctx = login(new_username, "password123")
    assert ctx.user_role == UserRole.COMPLIANCE

def test_admin_can_change_employee_to_compliance():
    admin_session = make_admin_session()
    target_username = make_test_username("lateral")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    admin_change_role(admin_session, target_username, UserRole.COMPLIANCE)

    ctx = login(target_username, "password123")
    assert ctx.user_role == UserRole.COMPLIANCE


def test_admin_can_change_compliance_to_employee():
    admin_session = make_admin_session()
    target_username = make_test_username("lateral2")
    create_user(target_username, "password123", UserRole.COMPLIANCE)

    admin_change_role(admin_session, target_username, UserRole.EMPLOYEE)

    ctx = login(target_username, "password123")
    assert ctx.user_role == UserRole.EMPLOYEE


def test_change_role_rejects_customer_target():
    admin_session = make_admin_session()
    target_username = make_test_username("nocustomer")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(UnauthorizedRoleError):
        admin_change_role(admin_session, target_username, UserRole.CUSTOMER)


def test_change_role_rejects_same_role():
    admin_session = make_admin_session()
    target_username = make_test_username("samerole")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(ValueError):
        admin_change_role(admin_session, target_username, UserRole.EMPLOYEE)


def test_non_admin_cannot_change_role():
    employee_session = make_employee_session()
    target_username = make_test_username("blocked2")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(UnauthorizedRoleError):
        admin_change_role(employee_session, target_username, UserRole.COMPLIANCE)

def test_cannot_change_role_of_last_admin():
    admin_username = make_test_username("onlyadmin")
    create_user(admin_username, "adminpass123", UserRole.ADMIN)
    admin_session = login(admin_username, "adminpass123").session_id

    # Temporarily deactivate every OTHER admin so this test's admin is
    # genuinely the last active one — necessary because we're testing
    # against the real shared database, which always has demo_admin
    # and possibly other admins already active.
    db = SessionLocal()
    try:
        other_admins = (
            db.query(User)
            .filter(User.role == DBUserRole.ADMIN, User.username != admin_username, User.is_active == True)  # noqa: E712
            .all()
        )
        other_admin_ids = [a.id for a in other_admins]
        for a in other_admins:
            a.is_active = False
        db.commit()
    finally:
        db.close()

    try:
        with pytest.raises(LastAdminError):
            admin_change_role(admin_session, admin_username, UserRole.EMPLOYEE)
    finally:
        # Always restore the other admins' active status, even if the
        # assertion above fails, so we don't leave demo_admin locked out.
        db = SessionLocal()
        try:
            db.query(User).filter(User.id.in_(other_admin_ids)).update(
                {"is_active": True}, synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

def test_can_change_role_when_multiple_admins_exist():
    admin1_username = make_test_username("admin1")
    admin2_username = make_test_username("admin2")
    create_user(admin1_username, "password123", UserRole.ADMIN)
    create_user(admin2_username, "password123", UserRole.ADMIN)
    admin1_session = login(admin1_username, "password123").session_id

    # demoting admin2 is fine, since admin1 remains
    admin_change_role(admin1_session, admin2_username, UserRole.EMPLOYEE)

    ctx = login(admin2_username, "password123")
    assert ctx.user_role == UserRole.EMPLOYEE


def test_cannot_deactivate_last_admin():
    admin_username = make_test_username("lastadmindeact")
    create_user(admin_username, "adminpass123", UserRole.ADMIN)
    admin_session = login(admin_username, "adminpass123").session_id

    db = SessionLocal()
    try:
        other_admins = (
            db.query(User)
            .filter(User.role == DBUserRole.ADMIN, User.username != admin_username, User.is_active == True)  # noqa: E712
            .all()
        )
        other_admin_ids = [a.id for a in other_admins]
        for a in other_admins:
            a.is_active = False
        db.commit()
    finally:
        db.close()

    try:
        with pytest.raises(LastAdminError):
            admin_deactivate_employee(admin_session, admin_username)
    finally:
        db = SessionLocal()
        try:
            db.query(User).filter(User.id.in_(other_admin_ids)).update(
                {"is_active": True}, synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

def test_can_deactivate_admin_when_multiple_exist():
    admin1_username = make_test_username("multiadmin1")
    admin2_username = make_test_username("multiadmin2")
    create_user(admin1_username, "password123", UserRole.ADMIN)
    create_user(admin2_username, "password123", UserRole.ADMIN)
    admin1_session = login(admin1_username, "password123").session_id

    admin_deactivate_employee(admin1_session, admin2_username)  # fine, admin1 remains active

    from agent1_classification.auth import InvalidCredentialsError
    with pytest.raises(InvalidCredentialsError):
        login(admin2_username, "password123")

def test_admin_add_employee_rejects_admin_role():
    """admin_add_employee should not be usable to create another Admin —
    that's admin_promote_to_admin's job."""
    admin_session = make_admin_session()
    new_username = make_test_username("sneakyadmin")

    with pytest.raises(UnauthorizedRoleError):
        admin_add_employee(admin_session, new_username, "password123", UserRole.ADMIN)


def test_non_admin_cannot_add_employee():
    employee_session = make_employee_session()
    new_username = make_test_username("blocked")

    with pytest.raises(UnauthorizedRoleError):
        admin_add_employee(employee_session, new_username, "password123", UserRole.EMPLOYEE)


# ---------- admin_promote_to_admin ----------

def test_admin_can_promote_employee_to_admin():
    admin_session = make_admin_session()
    target_username = make_test_username("promote")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    admin_promote_to_admin(admin_session, target_username)

    ctx = login(target_username, "password123")
    assert ctx.user_role == UserRole.ADMIN

def test_admin_can_demote_from_admin():
    admin_session = make_admin_session()
    target_username = make_test_username("demote")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    admin_promote_to_admin(admin_session, target_username)
    admin_demote_from_admin(admin_session, target_username, UserRole.EMPLOYEE)

    ctx = login(target_username, "password123")
    assert ctx.user_role == UserRole.EMPLOYEE


def test_demote_rejects_non_admin_role_target():
    admin_session = make_admin_session()
    target_username = make_test_username("baddemote")
    create_user(target_username, "password123", UserRole.EMPLOYEE)
    admin_promote_to_admin(admin_session, target_username)

    with pytest.raises(UnauthorizedRoleError):
        admin_demote_from_admin(admin_session, target_username, UserRole.ADMIN)


def test_demote_rejects_already_non_admin_user():
    admin_session = make_admin_session()
    target_username = make_test_username("notadminyet")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(ValueError):
        admin_demote_from_admin(admin_session, target_username, UserRole.EMPLOYEE)

def test_promote_nonexistent_user_raises():
    admin_session = make_admin_session()

    with pytest.raises(EmployeeNotFoundError):
        admin_promote_to_admin(admin_session, "test_does_not_exist_" + uuid.uuid4().hex[:8])


def test_non_admin_cannot_promote():
    employee_session = make_employee_session()
    target_username = make_test_username("cantpromote")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(UnauthorizedRoleError):
        admin_promote_to_admin(employee_session, target_username)


# ---------- admin_deactivate_employee / admin_reactivate_employee ----------

def test_admin_can_deactivate_employee():
    admin_session = make_admin_session()
    target_username = make_test_username("deactivate")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    admin_deactivate_employee(admin_session, target_username)

    from agent1_classification.auth import InvalidCredentialsError
    with pytest.raises(InvalidCredentialsError):
        login(target_username, "password123")


def test_admin_can_reactivate_employee():
    admin_session = make_admin_session()
    target_username = make_test_username("reactivate")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    admin_deactivate_employee(admin_session, target_username)
    admin_reactivate_employee(admin_session, target_username)

    ctx = login(target_username, "password123")
    assert ctx.user_role == UserRole.EMPLOYEE


def test_deactivate_nonexistent_user_raises():
    admin_session = make_admin_session()

    with pytest.raises(EmployeeNotFoundError):
        admin_deactivate_employee(admin_session, "test_ghost_" + uuid.uuid4().hex[:8])


def test_non_admin_cannot_deactivate():
    employee_session = make_employee_session()
    target_username = make_test_username("safe")
    create_user(target_username, "password123", UserRole.EMPLOYEE)

    with pytest.raises(UnauthorizedRoleError):
        admin_deactivate_employee(employee_session, target_username)


# ---------- admin_list_employees ----------

def test_admin_can_list_employees():
    admin_session = make_admin_session()
    username1 = make_test_username("list1")
    username2 = make_test_username("list2")
    create_user(username1, "password123", UserRole.EMPLOYEE)
    create_user(username2, "password123", UserRole.COMPLIANCE)

    employees = admin_list_employees(admin_session)
    usernames_found = {e.username for e in employees}

    assert username1 in usernames_found
    assert username2 in usernames_found


def test_non_admin_cannot_list_employees():
    employee_session = make_employee_session()

    with pytest.raises(UnauthorizedRoleError):
        admin_list_employees(employee_session)


# ---------- admin_add_document ----------

def test_admin_can_add_document():
    admin_session = make_admin_session()
    doc_id = make_test_doc_id("guide")

    result = admin_add_document(
        admin_session,
        doc_id=doc_id,
        title="Test Savings Guide",
        access_level=AccessLevel.PUBLIC,
        version="v1",
        effective_date=date(2026, 1, 1),
        file_path="/fake/path/guide.pdf",
    )

    assert result.doc_id == doc_id
    assert result.access_level == AccessLevel.PUBLIC
    assert result.is_current is True


def test_add_document_rejects_duplicate_doc_id():
    admin_session = make_admin_session()
    doc_id = make_test_doc_id("dup")

    admin_add_document(
        admin_session, doc_id, "First", AccessLevel.PUBLIC, "v1",
        date(2026, 1, 1), "/fake/path.pdf",
    )

    with pytest.raises(ValueError):
        admin_add_document(
            admin_session, doc_id, "Duplicate", AccessLevel.INTERNAL, "v1",
            date(2026, 1, 1), "/fake/other.pdf",
        )


def test_non_admin_cannot_add_document():
    employee_session = make_employee_session()
    doc_id = make_test_doc_id("blocked")

    with pytest.raises(UnauthorizedRoleError):
        admin_add_document(
            employee_session, doc_id, "Blocked Doc", AccessLevel.PUBLIC, "v1",
            date(2026, 1, 1), "/fake/path.pdf",
        )


# ---------- admin_retire_document ----------

def test_admin_can_retire_document():
    admin_session = make_admin_session()
    doc_id = make_test_doc_id("retire")

    admin_add_document(
        admin_session, doc_id, "To Retire", AccessLevel.RESTRICTED, "v1",
        date(2026, 1, 1), "/fake/path.pdf",
    )
    admin_retire_document(admin_session, doc_id)

    docs = admin_list_documents(admin_session, current_only=False)
    retired = next(d for d in docs if d.doc_id == doc_id)
    assert retired.is_current is False


def test_retire_nonexistent_document_raises():
    admin_session = make_admin_session()

    with pytest.raises(DocumentNotFoundError):
        admin_retire_document(admin_session, "test_doc_ghost_" + uuid.uuid4().hex[:8])


def test_non_admin_cannot_retire_document():
    admin_session = make_admin_session()
    employee_session = make_employee_session()
    doc_id = make_test_doc_id("protectedretire")

    admin_add_document(
        admin_session, doc_id, "Protected", AccessLevel.PUBLIC, "v1",
        date(2026, 1, 1), "/fake/path.pdf",
    )

    with pytest.raises(UnauthorizedRoleError):
        admin_retire_document(employee_session, doc_id)


# ---------- admin_list_documents ----------

def test_list_documents_current_only_filter():
    admin_session = make_admin_session()
    active_doc = make_test_doc_id("active")
    retired_doc = make_test_doc_id("retiredlisting")

    admin_add_document(
        admin_session, active_doc, "Active Doc", AccessLevel.PUBLIC, "v1",
        date(2026, 1, 1), "/fake/active.pdf",
    )
    admin_add_document(
        admin_session, retired_doc, "Retired Doc", AccessLevel.PUBLIC, "v1",
        date(2026, 1, 1), "/fake/retired.pdf",
    )
    admin_retire_document(admin_session, retired_doc)

    current_docs = admin_list_documents(admin_session, current_only=True)
    current_doc_ids = {d.doc_id for d in current_docs}

    assert active_doc in current_doc_ids
    assert retired_doc not in current_doc_ids