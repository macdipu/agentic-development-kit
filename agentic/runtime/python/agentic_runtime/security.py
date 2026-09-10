import re
PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
def redact(text: str) -> str:
    out = text
    for p in PATTERNS:
        out = p.sub("[REDACTED]", out)
    return out
