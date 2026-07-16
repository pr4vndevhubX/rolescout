"""Notification tests — digest rendering is pure; SMTP-off behavior is safe."""

from app.services.notification_service import render_digest, send_email, smtp_configured


MATCH = {
    "title": "Machine Learning Engineer",
    "company": "Acme AI",
    "location": "Remote",
    "blended_score": 0.82,
    "apply_url": "https://example.com/apply/1",
    "matched_skills": ["Python", "PyTorch"],
}


def test_digest_subject_counts_matches():
    subject, text, html = render_digest(user_name="Praveen", matches=[MATCH, {**MATCH, "title": "AI Engineer"}])
    assert "2 new job matches" in subject


def test_digest_mentions_tailoring():
    tailored = {**MATCH, "tailoring": {"honest_gaps": [{"skill": "Kubernetes"}]}}
    subject, text, html = render_digest(user_name=None, matches=[tailored])
    assert "1 resume-tailored" in subject
    assert "tailored" in text.lower()
    assert "Kubernetes" in text


def test_digest_bodies_contain_job_and_link():
    subject, text, html = render_digest(user_name="P", matches=[MATCH])
    for body in (text, html):
        assert "Machine Learning Engineer" in body
        assert "https://example.com/apply/1" in body
    assert "82%" in html


def test_send_email_degrades_gracefully_without_smtp(monkeypatch):
    # conftest never sets SMTP_HOST, so sending must be a safe no-op.
    assert smtp_configured() is False
    assert send_email(to="x@y.z", subject="s", html_body="<p>h</p>", text_body="t") is False
