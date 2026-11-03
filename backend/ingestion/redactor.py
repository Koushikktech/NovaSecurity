from __future__ import annotations

import re

# Common API key and secret patterns
SECRET_PATTERNS = [
    # AWS Access Key ID
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    # GitHub personal access tokens
    (re.compile(r"\b(gh[pousr]_[a-zA-Z0-9]{20,255})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\b(github_pat_[a-zA-Z0-9_]{82})\b"), "[REDACTED_GITHUB_PAT]"),
    # Google API Key
    (re.compile(r"\b(AIza[0-9A-Za-z-_]{35})\b"), "[REDACTED_GOOGLE_API_KEY]"),
    # OpenAI API Key
    (re.compile(r"\b(sk-(?:proj-|svcacct-)?[a-zA-Z0-9_-]{20,255})\b"), "[REDACTED_OPENAI_KEY]"),
    # Slack token
    (re.compile(r"\b(xox[baprs]-[0-9a-zA-Z-]{10,72})\b"), "[REDACTED_SLACK_TOKEN]"),
    # Credentials embedded in URLs and authorization headers.
    (re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@"), r"\1[REDACTED_CREDENTIALS]@"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{12,}={0,2}"), r"\1[REDACTED_BEARER]"),
    # Quoted dictionary/JSON secret values (in addition to assignments below).
    (
        re.compile(
            r"""(?i)(["'](?:password|secret|api_key|access_token|refresh_token|client_secret|private_key)["']\s*:\s*)["']([^"'\n]{8,})["']"""
        ),
        r'\1"[REDACTED_SECRET]"',
    ),
    # Private Key blocks
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Generic password assignments: password = "..." or secret = "..."
    (
        re.compile(r"""(?i)(password|secret|api_key|access_token|private_key)\s*[:=]\s*['"]([^\s'"]{8,})['"]"""),
        r'\1 = "[REDACTED_SECRET]"',
    ),
]


def redact_secrets(text: str) -> tuple[str, int]:
    """Scans and redacts detected secrets from source code or diffs.
    Returns (redacted_text, count_of_redactions).
    """
    redacted = text
    count = 0
    for pattern, replacement in SECRET_PATTERNS:
        matches = pattern.findall(redacted)
        if matches:
            count += len(matches)
            redacted = pattern.sub(replacement, redacted)
    return redacted, count


def redact_value(value):
    """Redact structured tool results before JSON escaping can hide source patterns."""
    if isinstance(value, str):
        return redact_secrets(value)[0]
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        secrets = {"password", "secret", "api_key", "access_token", "refresh_token", "client_secret", "private_key"}
        return {
            key: ("[REDACTED_SECRET]" if str(key).lower() in secrets and isinstance(item, str) else redact_value(item))
            for key, item in value.items()
        }
    return value
