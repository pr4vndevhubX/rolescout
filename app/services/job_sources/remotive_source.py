"""Remotive connector — free, keyless API for remote-only jobs (remotive.com)."""

import httpx

from app.services.job_sources.base import JobSource, JobSourceError
from app.services.job_sources.experience_extractor import extract_min_years_required
from app.services.job_sources.html_utils import strip_html

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    name = "remotive"
    requires_api_key = False

    def fetch(
        self,
        query: str,
        *,
        country: str = "gb",     # ignored — Remotive lists remote jobs worldwide
        location: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        try:
            response = httpx.get(API_URL, params={"search": query, "limit": limit}, timeout=20, verify=False)
            response.raise_for_status()
            raw_jobs = response.json().get("jobs", [])
        except Exception as e:
            raise JobSourceError(f"Remotive fetch failed: {e}") from e

        return [self._normalize(raw) for raw in raw_jobs[:limit]]

    @staticmethod
    def _normalize(raw: dict) -> dict:
        description = strip_html(raw.get("description", ""))
        return {
            "job_id": f"remotive_{raw.get('id')}",
            "title": (raw.get("title") or "").strip(),
            "company": raw.get("company_name"),
            "location": raw.get("candidate_required_location") or "Remote",
            "description": description,
            "salary_min": None,   # Remotive's salary field is free text — unusable as a number
            "salary_max": None,
            "remote": "yes",
            "min_years_required": extract_min_years_required(description),
            "apply_url": raw.get("url"),
            "source": "remotive",
        }
