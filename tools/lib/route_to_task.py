def choose_skill(query: str):
    if "比較" in query or "決め" in query:
        return "decision", "decision_keyword_match"
    return "research", "keyword match"
