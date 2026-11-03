"""Repository guidance is data; it cannot grant execution or credential permissions."""

from fnmatch import fnmatch

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RepositoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude: list[str] = Field(default_factory=list, max_length=100)
    focus: list[str] = Field(default_factory=list, max_length=20)
    verification_profile: str | None = None


def read_policy(files):
    source = next((f["content"] for f in files if f["relative_path"] == ".proofline.yml"), "")
    if len(source) > 32000:
        raise ValueError("Repository policy exceeds 32 KB")
    if not source:
        return RepositoryPolicy()
    return RepositoryPolicy.model_validate(yaml.safe_load(source) or {})


def excluded(path, policy):
    return any(fnmatch(path, pattern) for pattern in policy.exclude)
