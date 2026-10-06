# BankKMS --- Secure Multi-Agent Knowledge Management System for Banking

BankKMS is a secure, multi-agent Knowledge Management System developed
for the banking domain. It enables customers and authorized bank
personnel to retrieve relevant organizational knowledge through
natural-language interaction while enforcing role-appropriate access,
evidence grounding, verification, auditability, and human escalation.

The project demonstrates how Agentic AI and Retrieval-Augmented
Generation (RAG) can be applied to a knowledge-management problem in
which information differs by audience, sensitivity, and operational
purpose.

## Key Features

-   Six-agent AI pipeline with clearly separated responsibilities
-   Natural-language access to approved banking knowledge
-   Role-based knowledge access for Customer, Employee, and Compliance
    users
-   Administrative interface for user, document, and audit management
-   Semantic retrieval using Sentence Transformers
-   `all-MiniLM-L6-v2` embeddings with 384 dimensions
-   PostgreSQL + pgvector vector storage and similarity search
-   Supabase-hosted PostgreSQL database
-   Google Gemini for LLM-assisted classification, generation, and
    verification
-   Evidence-grounded answers with document citations
-   Current-document/version filtering during retrieval
-   Prompt-injection and adversarial-input controls
-   Independent response verification before release
-   Tamper-evident SHA-256 hash-chained audit logging
-   Human escalation for uncertain or high-risk cases
-   React/Vite frontend and FastAPI backend

## System Architecture

``` text
Users
├── Customer
├── Employee
├── Compliance Officer
└── Administrator
        │
        ▼
React + Vite Frontend
        │
        ▼
FastAPI Backend
        │
        ▼
┌──────────────────────────────────────────────┐
│ Agent 1 — Classification & Access Control    │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 2 — Knowledge Retrieval                │
│ Sentence Transformers + PostgreSQL/pgvector  │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 3 — Knowledge Analysis & Response      │
│ Grounded response generation + citations     │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 4 — Verification & Governance          │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 5 — Audit & Compliance Logging         │
│ SHA-256 hash-chained audit trail             │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 6 — Escalation & Human Handoff         │
└──────────────────────┬───────────────────────┘
                       ▼
                 Final Response
```

Agent 5 records pipeline activity for traceability, while Agent 6
evaluates whether a case requires human review.

## Agent Responsibilities

  -----------------------------------------------------------------------
  Agent                               Responsibility
  ----------------------------------- -----------------------------------
  Agent 1                             Resolves the user's session-derived
                                      role/access level, sanitizes input,
                                      classifies the query, and
                                      identifies suspicious input.

  Agent 2                             Embeds the normalized query,
                                      performs access-filtered semantic
                                      retrieval, filters to current
                                      documents, and returns supporting
                                      chunks.

  Agent 3                             Generates a response using
                                      retrieved evidence rather than
                                      unrestricted model knowledge and
                                      attaches source citations.

  Agent 4                             Independently checks evidence
                                      sufficiency, grounding, access
                                      compliance, confidence, and
                                      governance conditions before
                                      release.

  Agent 5                             Records important pipeline
                                      decisions in a tamper-evident
                                      SHA-256 hash chain for auditability
                                      and accountability.

  Agent 6                             Evaluates escalation conditions and
                                      routes uncertain or high-risk cases
                                      for human review.
  -----------------------------------------------------------------------

## Access Model

BankKMS separates knowledge access from user-supplied prompt text. A
user cannot obtain a higher access level simply by claiming a different
role in a query.

  -----------------------------------------------------------------------
  User Role                           Knowledge Access
  ----------------------------------- -----------------------------------
  Customer                            Public

  Employee                            Internal

  Compliance Officer                  Restricted

  Administrator                       Administrative functions only; no
                                      knowledge-base query access
  -----------------------------------------------------------------------

Customers can use the public knowledge interface without staff
authentication. Employee and Compliance access is tied to authenticated
sessions. Administrators manage system resources such as users,
documents, and audit information rather than acting as another
knowledge-access tier.

## Technology Stack

  Layer                 Technology
  --------------------- -----------------------------------
  Frontend              React, Vite
  Backend/API           FastAPI
  LLM                   Google Gemini
  Embeddings            Sentence Transformers
  Embedding Model       `all-MiniLM-L6-v2`
  Embedding Dimension   384
  Database              Supabase-hosted PostgreSQL
  Vector Search         pgvector
  ORM / DB Access       SQLAlchemy / PostgreSQL driver
  Testing               pytest and API-level test scripts
  Version Control       Git / GitHub

## Knowledge Retrieval

BankKMS uses semantic retrieval rather than relying only on keyword
matching.

1.  Approved source documents are ingested into the knowledge base.
2.  Documents are divided into retrievable chunks.
3.  Each chunk is converted to a 384-dimensional embedding using
    `all-MiniLM-L6-v2`.
4.  Embeddings are stored in the pgvector-enabled `document_chunks`
    table.
5.  A user's normalized query is embedded with the same model.
6.  Agent 2 performs vector similarity search while applying
    access-level and current-document filters.
7.  Relevant chunks are passed to Agent 3 as evidence.
8.  Agent 3 generates a grounded answer with citations.
9.  Agent 4 verifies the response before it is released.

## Database

The final system uses PostgreSQL with pgvector. Core tables include:

-   `users` --- authenticated user accounts and roles
-   `sessions` --- authenticated and anonymous session state
-   `documents` --- document metadata, access level, version
    information, and current-version state
-   `document_chunks` --- chunk text, source information, and
    384-dimensional vector embeddings
-   `audit_log` --- pipeline audit records and hash-chain integrity
    information

## Prerequisites

Install the following before running the project:

-   Python 3.x
-   Node.js and npm
-   PostgreSQL with the pgvector extension, or access to the configured
    Supabase PostgreSQL project
-   A Google Gemini API key
-   Git

## Installation

Clone the repository and enter the project directory:

``` bash
git clone <YOUR_REPOSITORY_URL>
cd bankkms
```

### Backend

Create and activate a Python virtual environment.

Windows:

``` bash
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the backend dependencies using the dependency file included in
the repository:

``` bash
pip install -r requirements.txt
```

> If the final repository keeps `requirements.txt` inside the backend
> directory, run the command from that directory or use its relative
> path.

### Frontend

Enter the frontend directory and install Node dependencies:

``` bash
cd frontend
npm install
```

## Environment Configuration

Create your local environment file from the example supplied with the
project.

``` bash
cp .env.example .env
```

On Windows, you can copy the file using File Explorer or:

``` powershell
Copy-Item .env.example .env
```

Configure the values required by your final repository. The important
deployment values include the PostgreSQL connection, Gemini credentials,
and embedding configuration.

Example:

``` env
DATABASE_URL=postgresql://<username>:<password>@<host>:<port>/<database>

LLM_API_KEY=<your-gemini-api-key>

EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

The embedding configuration must remain compatible with the database
schema:

``` text
Embedding model: all-MiniLM-L6-v2
Embedding dimension: 384
pgvector column dimension: 384
```

**Security:** never commit `.env`, live API keys, database passwords,
service-role credentials, or other secrets to GitHub. Example
environment files must contain placeholders only.

## Database Setup and Migration

Before starting the application:

1.  Create or select the PostgreSQL/Supabase database.
2.  Enable the pgvector extension.
3.  Configure `DATABASE_URL`.
4.  Run the database migration/setup mechanism included in the
    repository.
5.  Confirm that the core tables are available.
6.  Confirm that the `document_chunks.embedding` vector dimension is
    384.

Because repository layouts can change during development, use the
migration/setup script or command included in the final source tree
rather than creating production tables manually.

## Knowledge-Base Ingestion

After the database is configured, run the repository's
knowledge-ingestion process to:

-   load approved source documents;
-   extract document metadata;
-   split documents into chunks;
-   generate Sentence Transformer embeddings;
-   store chunks and embeddings in PostgreSQL/pgvector.

The final embedding provider must be:

``` env
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

After ingestion, verify that documents and document chunks exist in the
database before testing semantic retrieval.

## Running the Application

### Start the backend

Run the FastAPI application using the backend entry point provided in
the final repository. A typical FastAPI development command is:

``` bash
uvicorn <backend_entry_module>:app --reload
```

Use the actual module name from the final source tree in place of
`<backend_entry_module>`.

Once started, FastAPI's development API documentation is normally
available at:

``` text
http://localhost:8000/docs
```

### Start the frontend

From the frontend directory:

``` bash
npm run dev
```

Vite will print the local development URL in the terminal.

## Usage

### Customer

Customers can use the public chat interface to ask questions about
public banking products, services, and approved customer-facing
information.

### Employee

Authenticated employees can retrieve public and internal operational
knowledge according to the system's access hierarchy.

### Compliance Officer

Authenticated Compliance users can retrieve knowledge up to the
Restricted tier.

### Administrator

Administrators use administrative functions to manage users, documents,
and audit information. The Admin role is intentionally separated from
knowledge-query privileges.

## Security and Responsible AI

BankKMS uses defense in depth rather than relying on a single LLM prompt
or sanitizer.

### Access Control

Authorization is derived from trusted session state rather than
user-supplied role claims. Agent 2 applies access filters during
retrieval, and Agent 4 performs an additional governance check before
release.

### Grounding and Hallucination Control

Agent 3 is designed to answer from retrieved organizational evidence.
When sufficient evidence is unavailable, the system can deny or escalate
rather than fabricate an answer.

### Prompt-Injection Resistance

Input sanitization and suspicious-input detection provide an initial
defense. More importantly, access-controlled retrieval and independent
verification remain separate downstream controls so authorization does
not depend solely on prompt-injection detection.

### Auditability

Agent 5 records pipeline activity in a SHA-256 hash-chained audit log.
This supports traceability and tamper-evidence for later investigation.

### Human Oversight

Agent 6 supports human review for cases such as low-confidence
responses, suspicious activity, and governance conditions that should
not be resolved automatically.

### Privacy

Do not place real customer PII, credentials, API keys, or confidential
banking data in the demonstration knowledge base or repository.
Production deployment would require additional organizational privacy,
retention, monitoring, and regulatory controls.

## Testing

Install all backend test dependencies and run the project's automated
tests from the appropriate project directory:

``` bash
pytest
```

For more detailed output:

``` bash
pytest -v
```

Testing should cover:

-   agent-level functionality;
-   end-to-end pipeline integration;
-   access-control enforcement;
-   retrieval and grounding;
-   verification decisions;
-   audit logging;
-   escalation behavior;
-   malformed and ambiguous inputs;
-   prompt-injection/adversarial inputs;
-   privacy and session isolation.

Some integration tests require a configured PostgreSQL database and
Gemini API access.

## Project Structure

The exact final tree should be treated as authoritative. At a high
level, BankKMS is organized around the following components:

``` text
bankkms/
├── agent1_classification/
├── agent2_retrieval/
├── agent3_response/
├── agent4_verification/
├── agent5_audit/
├── agent6_escalation/
├── backend/
├── frontend/
├── knowledge_base/
├── shared/
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

If the final repository uses slightly different folder or entry-point
names, update this section to match the committed source tree before
submission.

## Team Contributions

BankKMS was developed collaboratively. All members contributed to
overall system planning, architecture, integration, frontend/backend
development, database and knowledge-base integration, testing,
debugging, Responsible AI and security considerations, documentation,
commercialization planning, and final project deliverables.

Primary agent ownership was:

  -----------------------------------------------------------------------
  Team Member                         Primary Agent Contribution
  ----------------------------------- -----------------------------------
  Member 1                            Agent 1 --- Classification & Access
                                      Control; Agent 5 --- Audit &
                                      Compliance Logging

  Member 2                            Agent 2 --- Knowledge Retrieval;
                                      Agent 6 --- Escalation & Human
                                      Handoff

  Member 3                            Agent 3 --- Knowledge Analysis &
                                      Response; Agent 6 --- Escalation &
                                      Human Handoff

  Member 4                            Agent 4 --- Verification &
                                      Governance; Agent 5 --- Audit &
                                      Compliance Logging
  -----------------------------------------------------------------------

Agent 5 was jointly developed by Members 1 and 4. Agent 6 was jointly
developed by Members 2 and 3.

Replace `Member 1`--`Member 4` with the final contributor names before
submission.

## Responsible Use

BankKMS is an academic prototype and is not a production banking system.
It should not be used to make real financial, regulatory, legal, or
compliance decisions without appropriate organizational controls and
human oversight.

## License

This repository was developed for academic purposes as part of IT3041
--- Information Retrieval and Web Analytics. Add a formal software
license only if one has been agreed by all contributors and is
appropriate for the project.
