"""
check_gemini_setup.py

Diagnostic matching the CURRENT verifier.py exactly -- checks LLM_API_KEY
first (your team's actual .env convention), and the current google-genai
SDK (not the deprecated google-generativeai package).

Run:
    python check_gemini_setup.py
"""

import os

from dotenv import load_dotenv

load_dotenv()

print("=== Env vars ===")
print("LLM_PROVIDER:        ", os.getenv("LLM_PROVIDER"))
print("LLM_MODEL:           ", os.getenv("LLM_MODEL"))
print("CONFIDENCE_THRESHOLD:", os.getenv("CONFIDENCE_THRESHOLD"))

key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
key_source = (
    "LLM_API_KEY" if os.getenv("LLM_API_KEY")
    else "GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY")
    else "GOOGLE_API_KEY" if os.getenv("GOOGLE_API_KEY")
    else None
)
print(f"API key found:       {bool(key)}", f"(via {key_source}, len={len(key)})" if key else "(MISSING)")

print("\n=== Package check ===")
try:
    from google import genai
    print("google-genai: installed OK")
except ImportError as e:
    print("google-genai: NOT INSTALLED ->", e)
    print("Fix: pip install google-genai")
    if _has_old_package := __import__("importlib.util", fromlist=["find_spec"]).find_spec("google.generativeai"):
        print("\nNOTE: the OLD deprecated 'google-generativeai' package IS installed.")
        print("That's not what verifier.py uses anymore -- it needs 'google-genai' instead.")
        print("pip uninstall google-generativeai && pip install google-genai")
    raise SystemExit(1)

if not key:
    print("\nNo API key found under LLM_API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY.")
    print("Fix: add LLM_API_KEY=your_key_here to your .env file")
    print("(LLM_API_KEY is the name Agents 1-3 use too -- keep it consistent.)")
    raise SystemExit(1)

print("\n=== Live call test ===")
try:
    client = genai.Client(api_key=key)
    model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    response = client.models.generate_content(
        model=model_name, contents="Reply with exactly: OK"
    )
    print("Gemini responded:", response.text.strip())
    print("\n✅ Gemini is wired up correctly.")
except Exception as e:
    print("Gemini call FAILED:", repr(e))
    print("\nCommon causes: invalid API key, wrong/retired model name, no internet, quota exceeded.")