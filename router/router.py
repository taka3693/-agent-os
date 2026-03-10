from dataclasses import dataclass

FIXED = [
    "critique",
    "decision",
    "experiment",
    "execution",
    "research",
    "retrospective",
]

FALLBACK = [
    "decision",
    "critique",
    "research",
    "execution",
]

MAX_CHAIN = 3


@dataclass
class RouteResult:
    skill: str | None
    reason: str


KEYWORDS = {
    "research": ["調査","調べ","比較","search","research"],
    "decision": ["決め","判断","迷","choose","decide"],
    "critique": ["レビュー","問題","弱点","review"],
    "execution": ["実装","作成","修正","update","implement"],
}


def keyword_route(text, allowed):
    text = text.lower()

    for skill in FIXED:
        if skill not in allowed:
            continue

        for w in KEYWORDS.get(skill, []):
            if w in text:
                return skill

    return None


def normalize(allowed):
    if not allowed:
        return FIXED.copy()

    result = []
    for s in allowed:
        if s in FIXED:
            result.append(s)

    return result


def route(text, allowed=None, chain=0):
    if chain >= MAX_CHAIN:
        return RouteResult(None, "chain limit")

    allowed = normalize(allowed)

    skill = keyword_route(text, allowed)

    if skill:
        return RouteResult(skill, "keyword match")

    for s in FALLBACK:
        if s in allowed:
            return RouteResult(s, "fallback")

    return RouteResult(None, "no skill")


if __name__ == "__main__":

    tests = [
        ("調査して比較したい", ["research","decision","execution"], 0),
        ("どう進めるべきか迷っている", ["decision","critique","execution"], 0),
        ("調査して比較したい", ["decision","execution"], 0),
    ]

    for text, allowed, chain in tests:
        r = route(text, allowed, chain)
        print(text, "->", r.skill, r.reason)
