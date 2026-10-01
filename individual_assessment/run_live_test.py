import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent1_classification.auth import register_session
from shared.enums import UserRole
from pipeline import run_pipeline

ROLE_MAP = {
    "customer": UserRole.CUSTOMER,
    "employee": UserRole.EMPLOYEE,
    "compliance": UserRole.COMPLIANCE,
}

if __name__ == "__main__":
    role_str = sys.argv[1]
    query = " ".join(sys.argv[2:])
    role = ROLE_MAP[role_str]
    session_id = f"test_{role_str}"

    register_session(session_id, role)
    result = run_pipeline(session_id, query)

    print("\n=== TEST RESULT ===")
    print(f"Role:    {role_str}")
    print(f"Query:   {query}")
    print(f"Status:  {result.get('status')}")
    print(f"Message: {result.get('message_to_user')}")

    if "agent3_output" in result:
        a3 = result["agent3_output"]
        print(f"Grounded:    {a3.grounded}")
        print(f"Chunks used: {a3.chunks_used}")
        print(f"Citations:   {[c.chunk_id for c in a3.citations]}")
        print(f"Notes:       {a3.synthesis_notes}")
    print("===================\n")