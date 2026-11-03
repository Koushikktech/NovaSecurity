"""Non-overridable credential-path exclusions; not a general secret detector."""

from pathlib import PurePosixPath

_SENSITIVE_DIRECTORIES = {".ssh", ".aws", ".azure", ".gcloud"}
_SENSITIVE_NAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
    "application_default_credentials.json",
}
_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template"}


def sensitive_source_path(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if not parts:
        return False
    lowered = [part.casefold() for part in parts]
    name = lowered[-1]
    if any(part in _SENSITIVE_DIRECTORIES for part in lowered):
        return True
    if name in _SENSITIVE_NAMES:
        return True
    if name not in _TEMPLATE_NAMES and (name == ".env" or name.startswith(".env.")):
        return True
    return PurePosixPath(name).suffix in {".pem", ".key", ".p12", ".pfx", ".keystore"}
