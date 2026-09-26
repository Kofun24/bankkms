"""
backend/main.py

Thin FastAPI layer exposing agent1_classification's auth + admin_operations
functions as HTTP endpoints, for the Admin Console React frontend to call.

Run from the repo root:
    python -m uvicorn backend.main:app --reload --port 8000
"""
import uuid
import sys
from datetime import date
from pathlib import Path
from typing import Optional
from database.config import SessionLocal
from database.models import AuditLog as AuditLogModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent1_classification.admin_operations import (
    DocumentNotFoundError,
    EmployeeNotFoundError,
    LastAdminError,
    admin_add_document,
    admin_add_employee,
    admin_change_role,
    admin_deactivate_employee,
    admin_list_documents,
    admin_list_employees,
    admin_promote_to_admin,
    admin_reactivate_employee,
    admin_retire_document,
)    
from agent1_classification.auth import (
    InvalidCredentialsError,
    UnauthorizedRoleError,
    end_session,
    login as auth_login,
)
from shared.enums import AccessLevel, UserRole

app = FastAPI(title="BankKMS Admin API")

# Vite's default dev server port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Helpers ----------------

def get_session_id(authorization: Optional[str] = Header(None)) -> str:
    """Extracts the session token from 'Authorization: Bearer <token>'."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    return authorization.removeprefix("Bearer ").strip()


def handle_common_errors(fn, *args, **kwargs):
    """Runs an admin_operations function and maps its exceptions to HTTP errors."""
    try:
        return fn(*args, **kwargs)
    except UnauthorizedRoleError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LastAdminError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (EmployeeNotFoundError, DocumentNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

# ---------------- Auth ----------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    session_id: str
    role: str
    access_level: str


@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    try:
        ctx = auth_login(payload.username, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if ctx.user_role != UserRole.ADMIN:
        end_session(ctx.session_id)
        raise HTTPException(status_code=403, detail="This console is for Admin accounts only.")

    return LoginResponse(
        session_id=ctx.session_id,
        role=ctx.user_role.value,
        access_level=ctx.access_level.value,
    )


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        end_session(authorization.removeprefix("Bearer ").strip())
    return {"status": "logged_out"}


# ---------------- Employees ----------------

class AddEmployeeRequest(BaseModel):
    username: str
    password: str
    role: str  # "employee" | "compliance"


class EmployeeResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


@app.get("/api/employees", response_model=list[EmployeeResponse])
def list_employees(authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    employees = handle_common_errors(admin_list_employees, session_id)
    return [
        EmployeeResponse(id=e.id, username=e.username, role=e.role.value, is_active=e.is_active)
        for e in employees
    ]


@app.post("/api/employees")
def add_employee(payload: AddEmployeeRequest, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role!r}")

    handle_common_errors(admin_add_employee, session_id, payload.username, payload.password, role)
    return {"status": "created"}


@app.post("/api/employees/{username}/deactivate")
def deactivate_employee(username: str, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    handle_common_errors(admin_deactivate_employee, session_id, username)
    return {"status": "deactivated"}


@app.post("/api/employees/{username}/reactivate")
def reactivate_employee(username: str, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    handle_common_errors(admin_reactivate_employee, session_id, username)
    return {"status": "reactivated"}


@app.post("/api/employees/{username}/promote")
def promote_employee(username: str, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    handle_common_errors(admin_promote_to_admin, session_id, username)
    return {"status": "promoted"}

class ChangeRoleRequest(BaseModel):
    new_role: str  # "employee" | "compliance" | "admin"


@app.post("/api/employees/{username}/change-role")
def change_role(username: str, payload: ChangeRoleRequest, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    try:
        new_role = UserRole(payload.new_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.new_role!r}")

    handle_common_errors(admin_change_role, session_id, username, new_role)
    return {"status": "role_changed"}

# ---------------- Documents ----------------

class AddDocumentRequest(BaseModel):
    doc_id: str
    title: str
    access_level: str  # "public" | "internal" | "restricted"
    version: str
    effective_date: date
    file_path: str


class DocumentResponse(BaseModel):
    id: int
    doc_id: str
    title: str
    access_level: str
    version: str
    is_current: bool


@app.get("/api/documents", response_model=list[DocumentResponse])
def list_documents(current_only: bool = False, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    docs = handle_common_errors(admin_list_documents, session_id, current_only)
    return [
        DocumentResponse(
            id=d.id, doc_id=d.doc_id, title=d.title,
            access_level=d.access_level.value, version=d.version, is_current=d.is_current,
        )
        for d in docs
    ]


@app.post("/api/documents")
def add_document(payload: AddDocumentRequest, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    try:
        access_level = AccessLevel(payload.access_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid access_level: {payload.access_level!r}")

    handle_common_errors(
        admin_add_document, session_id, payload.doc_id, payload.title,
        access_level, payload.version, payload.effective_date, payload.file_path,
    )
    return {"status": "created"}


@app.post("/api/documents/{doc_id}/retire")
def retire_document(doc_id: str, authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    handle_common_errors(admin_retire_document, session_id, doc_id)
    return {"status": "retired"}


# ---------------- Audit Log ----------------

class AuditLogEntry(BaseModel):
    id: int
    session_id: str
    stage: str
    agent: str
    decision_summary: str
    timestamp: str


@app.get("/api/audit-log", response_model=list[AuditLogEntry])
def get_audit_log(authorization: Optional[str] = Header(None), limit: int = 50):
    session_id = get_session_id(authorization)
    from agent1_classification.auth import require_admin
    handle_common_errors(require_admin, session_id)

    db = SessionLocal()
    try:
        records = (
            db.query(AuditLogModel)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            AuditLogEntry(
                id=r.id,
                session_id=r.session_id,
                stage=r.stage.value,
                agent=r.agent,
                decision_summary=r.decision_summary,
                timestamp=r.timestamp.isoformat(),
            )
            for r in records
        ]
    finally:
        db.close()


@app.get("/api/audit-log/verify")
def verify_audit_chain(authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    from agent1_classification.auth import require_admin
    handle_common_errors(require_admin, session_id)

    from agent5_audit_logging.logger import verify_chain
    is_intact, broken = verify_chain()
    return {"intact": is_intact, "broken_records": broken}


# ---------------- Dashboard stats ----------------

class DashboardStats(BaseModel):
    total_employees: int
    active_employees: int
    total_documents: int
    restricted_documents: int


@app.get("/api/dashboard-stats", response_model=DashboardStats)
def dashboard_stats(authorization: Optional[str] = Header(None)):
    session_id = get_session_id(authorization)
    employees = handle_common_errors(admin_list_employees, session_id)
    documents = handle_common_errors(admin_list_documents, session_id, False)

    return DashboardStats(
        total_employees=len(employees),
        active_employees=sum(1 for e in employees if e.is_active),
        total_documents=len(documents),
        restricted_documents=sum(1 for d in documents if d.access_level.value == "restricted"),
    )

# ---------------- Customer Chat (public, no auth) ----------------

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    status: str
    message_to_user: str
    needs_clarification: bool = False


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """
    Public endpoint — no Authorization header required. Anonymous
    customer sessions are auto-provisioned by the pipeline itself
    (require_query_access allows anonymous by design).
    """
    try:
        from pipeline import run_pipeline
    except ModuleNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Query pipeline not available on this branch yet: {e}",
        )

    result = run_pipeline(payload.session_id, payload.message)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("message", result["error"]))

    return ChatResponse(
        status=result.get("status", "unknown"),
        message_to_user=result.get("message_to_user", "Sorry, I couldn't process that."),
        needs_clarification=result.get("status") == "needs_clarification",
    )


@app.post("/api/chat/new-session")
def new_chat_session():
    """Generates a fresh anonymous session token for a new customer visitor."""
    return {"session_id": str(uuid.uuid4())}

# ---------------- Staff Login (Employee / Compliance) ----------------

class StaffLoginResponse(BaseModel):
    session_id: str
    username: str
    role: str
    access_level: str


@app.post("/api/staff/login", response_model=StaffLoginResponse)
def staff_login(payload: LoginRequest):
    try:
        ctx = auth_login(payload.username, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if ctx.user_role not in (UserRole.EMPLOYEE, UserRole.COMPLIANCE):
        end_session(ctx.session_id)
        raise HTTPException(
            status_code=403,
            detail="This portal is for employee and compliance accounts only.",
        )

    return StaffLoginResponse(
        session_id=ctx.session_id,
        username=payload.username,
        role=ctx.user_role.value,
        access_level=ctx.access_level.value,
    )