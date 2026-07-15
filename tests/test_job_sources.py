"""Connector-layer tests: normalization to the internal job shape + registry."""

import pytest

from app.services.job_sources.arbeitnow_source import ArbeitnowSource
from app.services.job_sources.base import JobSource
from app.services.job_sources.registry import available_sources, resolve_sources
from app.services.job_sources.remotive_source import RemotiveSource

REQUIRED_KEYS = {
    "job_id", "title", "company", "location", "description",
    "salary_min", "salary_max", "remote", "min_years_required",
    "apply_url", "source",
}


def test_all_three_sources_registered():
    assert available_sources() == ["adzuna", "arbeitnow", "remotive"]


def test_resolve_all_returns_every_source():
    assert len(resolve_sources("all")) == 3
    assert all(isinstance(s, JobSource) for s in resolve_sources(None))


def test_resolve_unknown_source_fails_loudly():
    with pytest.raises(ValueError, match="Unknown job source"):
        resolve_sources("linkedin")


def test_remotive_normalize_produces_internal_shape():
    raw = {
        "id": 12345,
        "title": " Machine Learning Engineer ",
        "company_name": "Acme AI",
        "candidate_required_location": "Worldwide",
        "description": "<p>We need <b>3+ years</b> of ML experience.</p>",
        "url": "https://remotive.com/job/12345",
    }
    job = RemotiveSource._normalize(raw)
    assert set(job.keys()) == REQUIRED_KEYS
    assert job["job_id"] == "remotive_12345"
    assert job["title"] == "Machine Learning Engineer"
    assert job["remote"] == "yes"
    assert "<p>" not in job["description"]          # HTML stripped
    assert job["min_years_required"] == 3.0          # parsed from description
    assert job["source"] == "remotive"


def test_arbeitnow_normalize_produces_internal_shape():
    raw = {
        "slug": "ai-engineer-berlin",
        "title": "AI Engineer",
        "company_name": "Beispiel GmbH",
        "location": "Berlin",
        "remote": False,
        "description": "<ul><li>Build LLM pipelines</li></ul>",
        "url": "https://arbeitnow.com/jobs/ai-engineer-berlin",
        "tags": ["python", "ml"],
    }
    job = ArbeitnowSource._normalize(raw)
    assert set(job.keys()) == REQUIRED_KEYS
    assert job["job_id"] == "arbeitnow_ai-engineer-berlin"
    assert job["remote"] == "no"
    assert "Build LLM pipelines" in job["description"]
    assert job["source"] == "arbeitnow"
