"""
Test bootstrap: guarantees required env vars exist BEFORE any app module is
imported (app.core.config fails fast on missing keys). Values are only
defaults — a real .env on the dev machine takes precedence.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
# At least one LLM provider must be configured for the app to boot.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
