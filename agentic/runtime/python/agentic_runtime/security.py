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


def redact_value(value):
    """Best-effort context/log hygiene, not a secret manager or DLP boundary."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(r"(?i)(password|secret|token|api[_-]?key|authorization)", str(key)) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value
