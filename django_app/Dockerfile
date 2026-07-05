# Django product-layer image. The CMD below (gunicorn) is the PRODUCTION
# entrypoint — this is what Cloud Run will actually execute in Phase 10.
# For local dev, docker-compose.yml overrides `command:` to run migrations
# and Django's dev server instead, so you get auto-reload and DEBUG=True
# without needing two separate Dockerfiles. Same image, different command
# depending on context — a normal and deliberate pattern.
FROM python:3.12-slim

WORKDIR /app

# uv installs fast and gives reproducible installs from uv.lock, same
# tool used throughout local dev — no reason to switch to plain pip here.
RUN pip install --no-cache-dir uv

# Copy dependency manifests first so Docker's layer cache is reused across
# builds whenever only application code changes, not dependencies — this is
# the single biggest thing that keeps rebuild times fast in this project,
# since the ai_service image (Phase 9's other Dockerfile) has genuinely
# heavy dependencies.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

EXPOSE 8000

# Production entrypoint (Phase 10 / Cloud Run). Local dev overrides this —
# see docker-compose.yml.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
