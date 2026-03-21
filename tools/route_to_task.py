def choose_skill(text: str):
    if "比較" in text or "決め" in text:
        return "decision", "decision_keyword_match"
    if "批判" in text or "レビュー" in text:
        return "critique", "critique_keyword_match"
    if "仮説" in text or "検証" in text:
        return "experiment", "experiment_keyword_match"
    if "実装" in text:
        return "execution", "execution_keyword_match"
    if "振り返" in text:
        return "retrospective", "retrospective_keyword_match"
    return "research", "fallback_research"
