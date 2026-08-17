"""
Quick diagnostic — run this to see exactly why Gemini isn't being called.

    python check_gemini_setup.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("=== Env vars ===")
print("LLM_PROVIDER:      ", os.getenv("LLM_PROVIDER"))
print("LLM_MODEL:          ", os.getenv("LLM_MODEL"))
print("CONFIDENCE_THRESHOLD:", os.getenv("CONFIDENCE_THRESHOLD"))
key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
print("GEMINI_API_KEY set:", bool(key), f"(len={len(key)})" if key else "(MISSING)")

print("\n=== Package check ===")
try:
    import google.generativeai as genai
    print("google-generativeai: installed OK")
except ImportError as e:
    print("google-generativeai: NOT INSTALLED ->", e)
    print("Fix: pip install google-generativeai")
    raise SystemExit(1)

if not key:
    print("\nNo API key found -> verifier.py will use the offline fallback.")
    print("Fix: add GEMINI_API_KEY=your_key_here to your .env file")
    raise SystemExit(1)

print("\n=== Live call test ===")
try:
    genai.configure(api_key=key)
    model = genai.GenerativeModel(os.getenv("LLM_MODEL", "gemini-2.0-flash"))
    response = model.generate_content("Reply with exactly: OK")
    print("Gemini responded:", response.text.strip())
    print("\n✅ Gemini is wired up correctly.")
except Exception as e:
    print("Gemini call FAILED:", repr(e))
    print("\nCommon causes: invalid API key, wrong model name, no internet, quota exceeded.")
