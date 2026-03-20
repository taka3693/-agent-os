import sys, json, re, subprocess
from skills.decision.generate_decision import generate_decision

args = sys.argv[1:]
fmt = "json"
out = None

i = 0
rest = []
while i < len(args):
    if args[i] == "--format" and i + 1 < len(args):
        fmt = args[i + 1]
        i += 2
    elif args[i] == "--out" and i + 1 < len(args):
        out = args[i + 1]
        i += 2
    else:
        rest.append(args[i])
        i += 1

user_input = rest[0] if rest else "no input"

NOISE = [
    "比較して決めたい", "比較して", "決めたい", "どっち", "どちら",
    "を比較", "比較", "おすすめ", "どれがいい", "が良い", "がいい",
    "重視で", "重視", "なら", "するなら"
]

PREFIX_PATTERNS = [
    r"^マネタイズ重視で\s*",
    r"^収益重視で\s*",
    r"^MVPを最速で出すなら\s*",
    r"^最速で出すなら\s*",
    r"^安全重視で\s*",
    r"^堅実にいくなら\s*",
]

def normalize_input(text: str) -> str:
    t = text.strip()
    for pat in PREFIX_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    return t

def clean_option(text: str) -> str:
    t = text.strip()
    for x in NOISE:
        t = t.replace(x, "")
    for pat in PREFIX_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(r"[？?]+", "", t)
    t = re.sub(r"\s+", " ", t).strip(" 、,.-")
    return t

def extract_options(text: str):
    if " vs " in text:
        parts = text.split(" vs ")
    elif "vs" in text:
        parts = text.split("vs")
    elif " or " in text:
        parts = text.split(" or ")
    elif "または" in text:
        parts = text.split("または")
    else:
        return ["option_a", "option_b"]
    opts = [clean_option(p) for p in parts]
    opts = [o for o in opts if o]
    return opts[:5] if len(opts) >= 2 else ["option_a", "option_b"]

def choose_preset(text: str):
    t = text.lower()
    if "収益" in text or "マネタイズ" in text or "monet" in t or "revenue" in t:
        return "monetization", {"impact": 5, "scalability": 5, "cost": 2, "speed": 3, "risk": 1}
    if "早く" in text or "最速" in text or "mvp" in t or "speed" in t:
        return "speed", {"impact": 4, "scalability": 3, "cost": 2, "speed": 5, "risk": 1}
    if "安全" in text or "risk" in t or "堅実" in text:
        return "safety", {"impact": 4, "scalability": 3, "cost": 2, "speed": 1, "risk": 5}
    return "default", None

normalized_input = normalize_input(user_input)
options = extract_options(normalized_input)
preset, weights = choose_preset(user_input)
result = generate_decision(user_input, options, weights=weights)
result["preset"] = preset

payload = {
    "selected_skill": "decision",
    "task_result": result
}

if fmt == "json":
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
elif fmt == "markdown":
    proc = subprocess.run(
        ["python3", "tools/render_decision_markdown.py"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    rendered = proc.stdout
elif fmt == "proposal":
    proc = subprocess.run(
        ["python3", "tools/render_decision_proposal.py"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    rendered = proc.stdout
else:
    raise SystemExit(f"unsupported format: {fmt}")

if out:
    with open(out, "w", encoding="utf-8") as f:
        f.write(rendered)

print(rendered, end="" if rendered.endswith("\n") else "\n")
