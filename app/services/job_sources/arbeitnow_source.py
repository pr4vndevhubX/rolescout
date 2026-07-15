"""Arbeitnow connector — free, keyless job-board API (arbeitnow.com), Europe/remote-heavy.

The API has no server-side search parameter, so results are filtered
client-side: a job matches if every term in the query appears in its
title/description/tags.
"""

import httpx

from app.services.job_sources.base import JobSource, JobSourceError
from app.services.job_sources.experience_extractor import extract_min_years_required
from app.services.job_sources.html_utils import strip_html

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(JobSource):
    name = "arbeitnow"
    requires_api_key = False

    def fetch(
        self,
        query: str,
        *,
        country: str = "gb",     # ignored — the API is a single worldwide board
        location: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        try:
            response = httpx.get(API_URL, timeout=20)
            response.raise_for_status()
            raw_jobs = response.json().get("data", [])
        except Exception as e:
            raise JobSourceError(f"Arbeitnow fetch failed: {e}") from e

        terms = [t for t in query.lower().split() if t]
        matches = []
        for raw in raw_jobs:
            haystack = " ".join([
                raw.get("title", ""),
                raw.get("description", ""),
                " ".join(raw.get("tags", [])),
            ]).lower()
            if all(term in haystack for term in terms):
                matches.append(self._normalize(raw))
            if len(matches) >= limit:
                break
        return matches

    @staticmethod
    def _normalize(raw: dict) -> dict:
        description = strip_html(raw.get("description", ""))
        return {
            "job_id": f"arbeitnow_{raw.get('slug')}",
            "title": (raw.get("title") or "").strip(),
            "company": raw.get("company_name"),
            "location": raw.get("location") or None,
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "remote": "yes" if raw.get("remote") else "no",
            "min_years_required": extract_min_years_required(description),
            "apply_url": raw.get("url"),
            "source": "arbeitnow",
        }
