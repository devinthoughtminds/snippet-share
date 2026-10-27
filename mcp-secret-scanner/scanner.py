"""Finds secrets in text with regular expressions. Plain Python, no MCP: server.py wraps it as tools.

shortcut: pattern matching only, so it misses secrets with no recognisable shape and can flag look-alikes;
add entropy checks or a tool like gitleaks if this ever guards something important.
"""

import re
from typing import NamedTuple


class Rule(NamedTuple):
    type: str
    pattern: re.Pattern
    show: int  # leading characters safe to show: a public prefix like "AKIA", never part of a password
    generic: bool = False  # generic rules also match placeholders such as "change-me", so those are skipped


# Specific rules first: when two rules match the same text, the earlier one wins.
# A named group `s` marks the secret itself; without it the whole match is the secret.
RULES = [
    Rule("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), 10),
    Rule("jwt", re.compile(r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}"), 3),
    Rule("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 4),
    Rule("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"), 4),
    Rule("google_api_key", re.compile(r"\bAIza[\w-]{35}"), 4),
    Rule("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), 5),
    Rule("api_key", re.compile(r"\bsk-(?:ant-|proj-)?[\w-]{20,}"), 3),
    Rule("url_password", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:(?P<s>[^\s:/@]+)@"), 0, generic=True),
    Rule(
        "password_assignment",
        re.compile(
            r"(?i)\b(?:\w*_)?(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
            r"[\"']?\s*[:=]\s*[\"'](?P<s>[^\"'\s]{8,})[\"']"
        ),
        0,
        generic=True,
    ),
    # .env style, upper-case names only, so `password = get_password()` in code isn't flagged.
    Rule(
        "env_secret",
        re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?[A-Z0-9_]*(?:PASSWORD|SECRET|API_KEY|TOKEN)[A-Z0-9_]*[ \t]*=[ \t]*(?P<s>[^\s\"'#]{8,})[ \t]*$"),
        0,
        generic=True,
    ),
]

PLACEHOLDER_STARTS = ("${", "<", "{{", "%(")
PLACEHOLDER_WORDS = ("change-me", "changeme", "your-", "your_", "example", "placeholder", "xxxx", "redacted", "dummy")


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    return lower.startswith(PLACEHOLDER_STARTS) or any(w in lower for w in PLACEHOLDER_WORDS)


def _matches(text: str) -> list[tuple[int, int, Rule]]:
    """(start, end, rule) for every secret, without overlaps, in text order."""
    kept: list[tuple[int, int, Rule]] = []
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            start, end = m.span("s") if "s" in rule.pattern.groupindex else m.span()
            if rule.generic and _is_placeholder(text[start:end]):
                continue
            if any(start < k_end and k_start < end for k_start, k_end, _ in kept):
                continue  # already reported by a more specific rule
            kept.append((start, end, rule))
    return sorted(kept, key=lambda k: k[0])


def scan(text: str) -> list[dict]:
    findings = []
    for start, end, rule in _matches(text):
        value = text[start:end]
        findings.append(
            {
                "type": rule.type,
                "line": text.count("\n", 0, start) + 1,
                "preview": f"{value[:rule.show]}... ({len(value)} chars)",
            }
        )
    return findings


def redact(text: str) -> str:
    # Replace from the end, so earlier offsets stay valid.
    for start, end, rule in reversed(_matches(text)):
        text = f"{text[:start]}[REDACTED:{rule.type}]{text[end:]}"
    return text
