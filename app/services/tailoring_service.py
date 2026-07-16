"""
Tailoring engine — adapts a resume to one specific job, truthfully.

Two operations, both grounded strictly in the parsed resume:
- tailor_resume_for_job: JSON suggestions (rewritten summary, bullet rewrites,
  truthfully surfaceable skills with evidence, ATS keywords, honest gaps).
- generate_cover_letter: 250-350 word letter body.

Both run on the "smart" tier of whatever LLM provider chain is configured.
"""

import json
import re

from app.ai.llm import llm_router
from app.ai.prompts.tailoring_prompts import (
    COVER_LETTER_SYSTEM_PROMPT,
    TAILORING_SYSTEM_PROMPT,
    build_cover_letter_prompt,
    build_tailoring_prompt,
)


class TailoringError(Exception):
    """Raised when the LLM output cannot be turned into a usable result."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


_EXPECTED_KEYS = {
    "tailored_summary": "",
    "bullet_rewrites": [],
    "surfaceable_skills": [],
    "ats_keywords_to_add": [],
    "honest_gaps": [],
}


def tailor_resume_for_job(
    *,
    resume_summary: str,
    job_title: str,
    company: str | None,
    job_description: str,
    missing_skills: list[str] | None = None,
    ats_missing_keywords: list[str] | None = None,
) -> dict:
    """Returns the tailoring suggestion dict (see _EXPECTED_KEYS for the shape)."""
    prompt = build_tailoring_prompt(
        resume_summary=resume_summary,
        job_title=job_title,
        company=company,
        job_description=job_description,
        missing_skills=missing_skills or [],
        ats_missing_keywords=ats_missing_keywords or [],
    )
    raw = llm_router.run(task="resume_tailoring", system=TAILORING_SYSTEM_PROMPT, prompt=prompt)

    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        raise TailoringError(f"Tailoring model returned invalid JSON: {e}") from e

    # Normalize to the expected shape — missing keys become safe empties so
    # downstream code (API, emails, UI) never branches on absence.
    return {key: data.get(key, default) for key, default in _EXPECTED_KEYS.items()}


def generate_cover_letter(
    *,
    resume_summary: str,
    candidate_name: str | None,
    job_title: str,
    company: str | None,
    job_description: str,
) -> str:
    """Returns the cover letter body text."""
    prompt = build_cover_letter_prompt(
        resume_summary=resume_summary,
        candidate_name=candidate_name,
        job_title=job_title,
        company=company,
        job_description=job_description,
    )
    letter = llm_router.run(task="cover_letter", system=COVER_LETTER_SYSTEM_PROMPT, prompt=prompt).strip()
    if len(letter) < 100:
        raise TailoringError("Cover letter output suspiciously short — refusing to store it.")
    return letter
