# In classifier.py, or a new small module like agent1_classification/fast_path.py

import re

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)\.?!?$", re.IGNORECASE),
    re.compile(r"^(bye|goodbye|see you|see ya|later)\.?!?$", re.IGNORECASE),
    re.compile(r"^(thanks?( you)?|thx|ty|ok(ay)?|cool|got it|great|nice)\.?!?$", re.IGNORECASE),
]

_FAST_PATH_RESPONSES = {
    "greeting": "Hi! I'm here to help with questions about our accounts, procedures, and policies. What would you like to know?",
    "farewell": "Take care! Feel free to come back anytime you have a question.",
    "acknowledgment": "You're welcome! Let me know if you have any other questions.",
}


def check_fast_path(raw_query: str) -> str | None:
    """
    Returns a canned response string if the message is small talk that
    doesn't warrant running the full pipeline, or None if it should go
    through normal classification/retrieval/generation.

    Deliberately conservative: only matches short, exact greeting/
    farewell/acknowledgment phrases — anything with real content
    (questions, longer messages) falls through to the full pipeline.
    """
    text = raw_query.strip()

    if len(text) > 40:
        return None  # too long to be simple small talk, run full pipeline

    for pattern in _GREETING_PATTERNS[:1]:
        if pattern.match(text):
            return _FAST_PATH_RESPONSES["greeting"]

    for pattern in _GREETING_PATTERNS[1:2]:
        if pattern.match(text):
            return _FAST_PATH_RESPONSES["farewell"]

    for pattern in _GREETING_PATTERNS[2:3]:
        if pattern.match(text):
            return _FAST_PATH_RESPONSES["acknowledgment"]

    return None