from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    # Load .env from backend directory or parent directory if present
    backend_env = Path(__file__).parent / ".env"
    parent_env = Path(__file__).parent.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif parent_env.exists():
        load_dotenv(parent_env)
    else:
        load_dotenv()
except ImportError:
    pass


class ProoflineSettings(BaseModel):
    llm_provider: str = Field(default_factory=lambda: os.getenv("PROOFLINE_LLM_PROVIDER", "gemini"))
    codex_cli_enabled: bool = Field(
        default_factory=lambda: os.getenv("PROOFLINE_CODEX_CLI_ENABLED", "false").lower() == "true"
    )
    codex_cli_path: str = Field(default_factory=lambda: os.getenv("PROOFLINE_CODEX_CLI_PATH", "codex"))
    codex_model: str = Field(default_factory=lambda: os.getenv("PROOFLINE_CODEX_MODEL", "auto"))
    codex_reasoning: str = Field(default_factory=lambda: os.getenv("PROOFLINE_CODEX_REASONING", "high"))
    codex_request_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("PROOFLINE_CODEX_REQUEST_TIMEOUT_SECONDS", "120"))
    )

    gemini_api_mode: str = Field(default_factory=lambda: os.getenv("PROOFLINE_GEMINI_API_MODE", "auto"))
    # Gemini configuration
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_review_model: str = Field(default_factory=lambda: os.getenv("PROOFLINE_GEMINI_REVIEW_MODEL", ""))
    gemini_patch_model: str = Field(
        default_factory=lambda: (
            os.getenv("PROOFLINE_GEMINI_PATCH_MODEL") or os.getenv("PROOFLINE_GEMINI_REVIEW_MODEL", "")
        )
    )
    gemini_reasoning_model: str = Field(
        default_factory=lambda: (
            os.getenv("PROOFLINE_GEMINI_REASONING_MODEL") or os.getenv("PROOFLINE_GEMINI_REVIEW_MODEL", "")
        )
    )

    # LLM operational limits
    llm_max_concurrency: int = Field(default_factory=lambda: int(os.getenv("PROOFLINE_LLM_MAX_CONCURRENCY", "2")))
    llm_request_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("PROOFLINE_LLM_REQUEST_TIMEOUT_SECONDS", "45"))
    )
    review_deadline_seconds: int = Field(
        default_factory=lambda: int(os.getenv("PROOFLINE_REVIEW_DEADLINE_SECONDS", "180"))
    )
    llm_max_attempts: int = Field(default_factory=lambda: int(os.getenv("PROOFLINE_LLM_MAX_ATTEMPTS", "3")))
    max_model_calls_per_run: int = Field(
        default_factory=lambda: int(os.getenv("PROOFLINE_MAX_MODEL_CALLS_PER_RUN", "12"))
    )
    max_output_tokens: int = Field(default_factory=lambda: int(os.getenv("PROOFLINE_MAX_OUTPUT_TOKENS", "4096")))
    max_context_tokens: int = Field(default_factory=lambda: int(os.getenv("PROOFLINE_MAX_CONTEXT_TOKENS", "24000")))

    # Persistence & paths
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "PROOFLINE_DATABASE_URL", f"sqlite:///{Path(__file__).parent / 'data' / 'proofline.db'}"
        )
    )
    artifact_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("PROOFLINE_ARTIFACT_DIR", str(Path(__file__).parent / "data" / "artifacts"))
        )
    )
    workspace_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("PROOFLINE_WORKSPACE_DIR", str(Path(__file__).parent / "data" / "workspaces"))
        )
    )

    # Server & security
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv(
                "PROOFLINE_ALLOWED_ORIGINS",
                "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000",
            ).split(",")
            if o.strip()
        ]
    )
    execution_enabled: bool = Field(
        default_factory=lambda: os.getenv("PROOFLINE_EXECUTION_ENABLED", "false").lower() in ("true", "1")
    )
    github_publish_enabled: bool = Field(
        default_factory=lambda: os.getenv("PROOFLINE_GITHUB_PUBLISH_ENABLED", "false").lower() in ("true", "1")
    )
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))

    def ensure_directories(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        # Ensure database directory exists if sqlite
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = ProoflineSettings()
settings.ensure_directories()
