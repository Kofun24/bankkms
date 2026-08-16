def classify(question: str, user_role: str) -> dict:
    # TODO: replace with real classification logic
    return {
        "user_role": user_role,
        "intent": "unknown",
        "topic": "unknown",
        "access_level": "public",
        "original_question": question,
        "needs_clarification": False,
        "clarification_question": None,
    }


if __name__ == "__main__":
    print(classify("What documents do I need to open a savings account?", "customer"))