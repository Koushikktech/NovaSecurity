FROM node:22-bookworm-slim AS parser
WORKDIR /parser
RUN npm install --ignore-scripts --no-audit --no-fund typescript@5.9.3

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=parser /usr/local/bin/node /usr/local/bin/node
COPY --from=parser /parser/node_modules/typescript /app/frontend/node_modules/typescript
RUN pip install --no-cache-dir uv==0.12.2
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --frozen --no-dev --no-install-project --project /app/backend
COPY backend /app/backend
COPY scripts /app/scripts
COPY fixtures /app/fixtures
RUN useradd --uid 10001 --create-home proofline && mkdir -p /app/data && chown 10001:10001 /app/data
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH=/app/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHON_DOTENV_DISABLED=1 \
    PROOFLINE_DATABASE_URL=sqlite:////app/data/proofline.db \
    PROOFLINE_WORKSPACE_DIR=/app/data/workspaces \
    PROOFLINE_ARTIFACT_DIR=/app/data/artifacts
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/healthz',headers={'Authorization':'Bearer '+os.getenv('PROOFLINE_OPERATOR_TOKEN','')}); urllib.request.urlopen(r,timeout=3).close()"
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
