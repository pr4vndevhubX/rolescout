"""Tailoring engine tests — LLM calls are monkeypatched, logic is real."""

import json

import pytest

import app.services.tailoring_service as tailoring
from app.services.tailoring_service import (
    TailoringError,
    generate_cover_letter,
    tailor_resume_for_job,
)


GOOD_TAILORING_JSON = {
    "tailored_summary": "ML engineer with 3 years of Python...",
    "bullet_rewrites": [{"original": "built APIs", "rewritten": "built ML-serving APIs"}],
    "surfaceable_skills": [{"skill": "Docker", "evidence": "deployed services in containers"}],
    "ats_keywords_to_add": ["MLOps"],
    "honest_gaps": [{"skill": "Kubernetes", "suggestion": "CKA course"}],
}


def _patch_llm(monkeypatch, response: str):
    calls = {}

    def fake_run(*, task, prompt, system=None, **overrides):
        calls["task"] = task
        calls["prompt"] = prompt
        calls["system"] = system
        return response

    monkeypatch.setattr(tailoring.llm_router, "run", fake_run)
    return calls


def test_tailoring_parses_and_normalizes_output(monkeypatch):
    calls = _patch_llm(monkeypatch, json.dumps(GOOD_TAILORING_JSON))
    result = tailor_resume_for_job(
        resume_summary="summary",
        job_title="ML Engineer",
        company="Acme",
        job_description="desc",
        missing_skills=["Kubernetes"],
    )
    assert calls["task"] == "resume_tailoring"
    assert result == GOOD_TAILORING_JSON
    assert "never invent" in calls["system"].lower() or "never invent" in calls["system"]


def test_tailoring_fills_missing_keys_with_safe_defaults(monkeypatch):
    _patch_llm(monkeypatch, json.dumps({"tailored_summary": "only this"}))
    result = tailor_resume_for_job(
        resume_summary="s", job_title="t", company=None, job_description="d",
    )
    assert result["tailored_summary"] == "only this"
    assert result["bullet_rewrites"] == []
    assert result["honest_gaps"] == []


def test_tailoring_strips_markdown_fences(monkeypatch):
    fenced = "```json\n" + json.dumps(GOOD_TAILORING_JSON) + "\n```"
    _patch_llm(monkeypatch, fenced)
    result = tailor_resume_for_job(
        resume_summary="s", job_title="t", company=None, job_description="d",
    )
    assert result["ats_keywords_to_add"] == ["MLOps"]


def test_tailoring_invalid_json_raises(monkeypatch):
    _patch_llm(monkeypatch, "sorry, I can't do JSON today")
    with pytest.raises(TailoringError, match="invalid JSON"):
        tailor_resume_for_job(
            resume_summary="s", job_title="t", company=None, job_description="d",
        )


def test_cover_letter_returns_body(monkeypatch):
    letter = "Dear Hiring Manager,\n" + ("I build ML systems. " * 20) + "\nRegards, A"
    calls = _patch_llm(monkeypatch, letter)
    result = generate_cover_letter(
        resume_summary="s", candidate_name="A", job_title="t",
        company="Acme", job_description="d",
    )
    assert calls["task"] == "cover_letter"
    assert result == letter.strip()


def test_cover_letter_too_short_raises(monkeypatch):
    _patch_llm(monkeypatch, "ok")
    with pytest.raises(TailoringError, match="short"):
        generate_cover_letter(
            resume_summary="s", candidate_name=None, job_title="t",
            company=None, job_description="d",
        )
