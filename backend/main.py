"""
backend/main.py

Thin FastAPI layer exposing agent1_classification's auth + admin_operations
functions as HTTP endpoints, for the Admin Console React frontend to call.

Run from the repo root:
    python -m uvicorn backend.main:app --reload --port 8000
"""
import uuid
import sys
from pathlib import Path
from typing import Optional
from database.config import SessionLocal
from database.models import AuditLog as AuditLogModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
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
    NoQueryAccessError,
    end_session,
    login as auth_login,
)
from agent2_retrieval.frontmatter import parse_frontmatter, MissingFrontmatterError
from agent2_retrieval.ingest import ingest_document_by_id, DocumentNotFoundError as IngestDocNotFoundError
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

# Documents are sorted into these folders by their frontmatter's access_level,
# mirroring the layout under knowledge_base/ used by the bulk ingestion path.
KNOWLEDGE_BASE_ROOT = Path(__file__).resolve().parent.parent / "knowledge_base"
ACCESS_LEVEL_FOLDER = {
    AccessLevel.PUBLIC: "public",
    AccessLevel.INTERNAL: "internal",
    AccessLevel.RESTRICTED: "restricted",
}


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
async def add_document(file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    """
    Accepts a document file directly (multipart upload). All metadata
    (doc_id, title, access_level, version, effective_date) is read from
    the file's own YAML frontmatter — not from separate form fields — so
    the file's declared access_level is always what's stored, with no
    risk of a form dropdown disagreeing with the document's own content.

    Flow: parse frontmatter -> route to knowledge_base/{access_level}/ ->
    save file -> create Document row -> immediately chunk + embed, so the
    document is searchable by the time this request returns.
    """
    session_id = get_session_id(authorization)

    raw_bytes = await file.read()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text (e.g. .md).")

    try:
        frontmatter = parse_frontmatter(raw_text)
    except MissingFrontmatterError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        access_level = AccessLevel(frontmatter["access_level"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Frontmatter access_level must be one of public/internal/restricted, "
                   f"got {frontmatter.get('access_level')!r}",
        )

    required_fields = ["doc_id", "doc_title", "version", "effective_date"]
    missing = [f for f in required_fields if f not in frontmatter]
    if missing:
        raise HTTPException(status_code=400, detail=f"Frontmatter missing required field(s): {missing}")

    # Route to the correct folder purely from the file's own declared access_level.
    folder = ACCESS_LEVEL_FOLDER[access_level]
    dest_path = KNOWLEDGE_BASE_ROOT / folder / file.filename
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(raw_text, encoding="utf-8")

    handle_common_errors(
        admin_add_document,
        session_id,
        frontmatter["doc_id"],
        frontmatter["doc_title"],
        access_level,
        str(frontmatter["version"]),
        frontmatter["effective_date"],
        str(dest_path),
    )

    try:
        chunks_written = ingest_document_by_id(frontmatter["doc_id"])
    except IngestDocNotFoundError as e:
        # Should not happen — we just created the row above — but surfaced
        # clearly rather than silently swallowed if it somehow does.
        raise HTTPException(status_code=500, detail=f"Document row missing immediately after creation: {e}")
    except FileNotFoundError as e:
        # Also shouldn't happen here since we just wrote the file ourselves,
        # but kept as a safety net consistent with ingest_document_by_id's contract.
        return {
            "status": "created_metadata_only",
            "doc_id": frontmatter["doc_id"],
            "warning": str(e),
        }

    return {
        "status": "created",
        "doc_id": frontmatter["doc_id"],
        "access_level": access_level.value,
        "saved_to": str(dest_path),
        "chunks_indexed": chunks_written,
    }


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


class CitationItem(BaseModel):
    doc_id: str
    doc_title: str
    section: str
    version: Optional[str] = None
    effective_date: Optional[str] = None


class FinalResponseData(BaseModel):
    answer: str
    citations: list[CitationItem] = []


class ChatResponse(BaseModel):
    status: str
    message_to_user: str
    needs_clarification: bool = False
    final_response: Optional[FinalResponseData] = None
    version_conflict_detected: Optional[bool] = False
    denial_reason: Optional[str] = None
    access_level: Optional[str] = None


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
    try:
        result = run_pipeline(payload.session_id, payload.message)
    except NoQueryAccessError as e:
        raise HTTPException(
            status_code=403,
            detail="This session is not authorized to query the knowledge base.",
        )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("message", result["error"]))

    agent4 = result.get("agent4_output")
    agent2 = result.get("agent2_output")
    agent1 = result.get("agent1_output")

    version_lookup = {}
    if agent2 and hasattr(agent2, "results"):
        for chunk in agent2.results:
            chunk_doc_id = getattr(chunk, "doc_id", None)
            if chunk_doc_id and chunk_doc_id not in version_lookup:
                version_lookup[chunk_doc_id] = {
                    "version": getattr(chunk, "doc_version", None),
                    "effective_date": getattr(chunk, "effective_date", None),
                }

    final_resp = None
    if result.get("final_response"):
        raw_final = result["final_response"]
        citations_list = []
        for c in raw_final.get("citations", []):
            doc_id = getattr(c, "doc_id", c.get("doc_id", "") if isinstance(c, dict) else "")
            doc_title = getattr(c, "doc_title", c.get("doc_title", "") if isinstance(c, dict) else "")
            section = getattr(c, "section", c.get("section", "") if isinstance(c, dict) else "")
            extra = version_lookup.get(doc_id, {})
            citations_list.append(CitationItem(
                doc_id=doc_id,
                doc_title=doc_title,
                section=section,
                version=extra.get("version"),
                effective_date=extra.get("effective_date"),
            ))
        final_resp = FinalResponseData(
            answer=raw_final.get("answer", ""),
            citations=citations_list,
        )

    version_conflict = getattr(agent4, "version_conflict_detected", False) if agent4 else False
    denial_reason = getattr(agent4, "denial_reason", None) if agent4 else None
    access_lvl = getattr(agent1, "access_level", None)
    if hasattr(access_lvl, "value"):
        access_lvl = access_lvl.value

    return ChatResponse(
        status=result.get("status", "unknown"),
        message_to_user=result.get("message_to_user", "Sorry, I couldn't process that."),
        needs_clarification=result.get("status") == "needs_clarification",
        final_response=final_resp,
        version_conflict_detected=bool(version_conflict),
        denial_reason=str(denial_reason) if denial_reason else None,
        access_level=str(access_lvl) if access_lvl else None,
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