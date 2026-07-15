import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

# --- LLM providers -----------------------------------------------------------
# Every provider below speaks the OpenAI-compatible chat completions API, so
# configuring ANY ONE of them is enough to run the whole system. Free options
# (Groq / Gemini free tiers, Ollama fully local) mean no paid OpenAI key is
# required. When several are configured, LLM_PROVIDER_PRIORITY decides order
# and the router fails over automatically when one errors or rate-limits.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")  # e.g. http://localhost:11434/v1

LLM_PROVIDER_PRIORITY = [
    p.strip().lower()
    for p in os.getenv("LLM_PROVIDER_PRIORITY", "groq,gemini,openrouter,openai,ollama").split(",")
    if p.strip()
]

# Per-provider model tiers: "fast" for cheap structured extraction,
# "smart" for reasoning/generation (tailoring, cover letters, agent planning).
# Every value is overridable from .env without touching code.
LLM_MODELS: dict[str, dict[str, str]] = {
    "openai": {
        "fast": os.getenv("OPENAI_FAST_MODEL", "gpt-4.1-mini"),
        "smart": os.getenv("OPENAI_SMART_MODEL", "gpt-4.1"),
    },
    "groq": {
        "fast": os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant"),
        "smart": os.getenv("GROQ_SMART_MODEL", "llama-3.3-70b-versatile"),
    },
    "gemini": {
        "fast": os.getenv("GEMINI_FAST_MODEL", "gemini-2.0-flash"),
        "smart": os.getenv("GEMINI_SMART_MODEL", "gemini-2.5-flash"),
    },
    "openrouter": {
        "fast": os.getenv("OPENROUTER_FAST_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        "smart": os.getenv("OPENROUTER_SMART_MODEL", "deepseek/deepseek-chat-v3-0324:free"),
    },
    "ollama": {
        "fast": os.getenv("OLLAMA_FAST_MODEL", "llama3.1"),
        "smart": os.getenv("OLLAMA_SMART_MODEL", "llama3.1"),
    },
}

_PROVIDER_KEYS = {
    "openai": OPENAI_API_KEY,
    "groq": GROQ_API_KEY,
    "gemini": GEMINI_API_KEY,
    "openrouter": OPENROUTER_API_KEY,
    "ollama": OLLAMA_BASE_URL,  # no key needed — configured iff a base URL is set
}

CONFIGURED_LLM_PROVIDERS = [
    name for name in LLM_PROVIDER_PRIORITY if _PROVIDER_KEYS.get(name)
]

if not CONFIGURED_LLM_PROVIDERS:
    raise RuntimeError(
        "No LLM provider configured. Set at least one of GROQ_API_KEY (free tier), "
        "GEMINI_API_KEY (free tier), OLLAMA_BASE_URL (local, free), "
        "OPENROUTER_API_KEY, or OPENAI_API_KEY in .env"
    )

# --- Job sources (all optional — keyless sources always work) ----------------
# Adzuna is the only keyed source; without keys it is skipped with a warning
# while Remotive/Arbeitnow (free, keyless) keep the pipeline alive.
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

# --- Auth (JWT) ---
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET not set in .env — generate a long random string.")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h default

# --- Optional: production hardening ---
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# --- Notifications (email digests / alerts; unset = notifications logged only) ---
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "assistant@localhost")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() != "false"

# --- Optional: background job sync (scheduler stays off unless queries are set) ---
_sync_queries_raw = os.getenv("JOB_SYNC_QUERIES", "")
JOB_SYNC_QUERIES = [q.strip() for q in _sync_queries_raw.split(";") if q.strip()]
JOB_SYNC_INTERVAL_HOURS = int(os.getenv("JOB_SYNC_INTERVAL_HOURS", "6"))
JOB_SYNC_COUNTRY = os.getenv("JOB_SYNC_COUNTRY", "gb")

# --- Assistant (daily autonomous run; opt-in) ---
ASSISTANT_DAILY_HOUR = int(os.getenv("ASSISTANT_DAILY_HOUR", "6"))  # local server time
ASSISTANT_ENABLED = os.getenv("ASSISTANT_ENABLED", "false").lower() == "true"
