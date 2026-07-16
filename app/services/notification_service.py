"""
Notifications — email delivery + digest rendering.

Design:
- SMTP settings come from .env (works with Gmail app-passwords, Mailgun,
  Brevo free tier, etc.). When SMTP is NOT configured, sending degrades to a
  log line and returns False — the pipeline never crashes over email.
- The digest renderer is pure (dicts in, strings out) so it is unit-testable
  without a mail server.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core import config

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(config.SMTP_HOST)


def send_email(*, to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Sends one email. Returns True on success, False when SMTP is unavailable."""
    if not smtp_configured():
        logger.info("SMTP not configured — would have emailed %s: %s", to, subject)
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.SMTP_FROM
    message["To"] = to
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            if config.SMTP_STARTTLS:
                server.starttls()
            if config.SMTP_USERNAME and config.SMTP_PASSWORD:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_FROM, [to], message.as_string())
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        logger.exception("Email delivery to %s failed", to)
        return False


# ---------- digest rendering (pure functions) ----------

def _format_match_text(m: dict) -> str:
    lines = [
        f"• {m['title']}" + (f" at {m['company']}" if m.get("company") else ""),
        f"  Fit: {round(m['blended_score'] * 100)}%"
        + (f" | Location: {m['location']}" if m.get("location") else ""),
    ]
    if m.get("matched_skills"):
        lines.append(f"  Matched skills: {', '.join(m['matched_skills'][:8])}")
    if m.get("tailoring"):
        gaps = [g.get("skill", "") for g in m["tailoring"].get("honest_gaps", [])][:5]
        lines.append("  ✂ Resume tailored for this JD"
                     + (f" (gaps to mention honestly: {', '.join(gaps)})" if gaps else ""))
    if m.get("apply_url"):
        lines.append(f"  Apply: {m['apply_url']}")
    return "\n".join(lines)


def _format_match_html(m: dict) -> str:
    score = round(m["blended_score"] * 100)
    company = f" at {m['company']}" if m.get("company") else ""
    location = f" · {m['location']}" if m.get("location") else ""
    skills = ", ".join(m.get("matched_skills", [])[:8])
    tailored = ""
    if m.get("tailoring"):
        tailored = "<div style='color:#7c3aed;font-size:13px'>✂ Resume tailored for this JD — suggestions attached in your dashboard</div>"
    apply_link = (
        f"<a href='{m['apply_url']}' style='color:#4f46e5'>Apply now →</a>"
        if m.get("apply_url") else ""
    )
    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:8px 0">
      <div style="font-weight:600">{m['title']}{company}</div>
      <div style="color:#6b7280;font-size:13px">Fit score: {score}%{location}</div>
      {f"<div style='font-size:13px'>Matched: {skills}</div>" if skills else ""}
      {tailored}
      {apply_link}
    </div>"""


def render_digest(*, user_name: str | None, matches: list[dict]) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for a daily digest.

    Each match dict needs: title, company, location, blended_score, apply_url,
    matched_skills; optionally "tailoring" (the tailor suggestion dict).
    """
    count = len(matches)
    tailored_count = sum(1 for m in matches if m.get("tailoring"))
    subject = f"🎯 {count} new job match{'es' if count != 1 else ''} for you"
    if tailored_count:
        subject += f" ({tailored_count} resume-tailored)"

    greeting = f"Hi {user_name}," if user_name else "Hi,"
    text_body = "\n\n".join([
        greeting,
        f"Your job assistant found {count} new matching job{'s' if count != 1 else ''} today:",
        *(_format_match_text(m) for m in matches),
        "Open your dashboard to review, tailor further, or mark as applied.",
    ])

    html_body = f"""
    <div style="font-family:system-ui,sans-serif;max-width:640px;margin:auto">
      <h2 style="color:#111827">Your daily job matches</h2>
      <p>{greeting} your assistant found <b>{count}</b> new matching job{'s' if count != 1 else ''} today:</p>
      {''.join(_format_match_html(m) for m in matches)}
      <p style="color:#6b7280;font-size:13px">
        Open your dashboard to review details, tailor your resume further, or mark jobs as applied.
      </p>
    </div>"""
    return subject, text_body, html_body
