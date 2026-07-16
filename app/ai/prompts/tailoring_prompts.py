"""
Prompts for resume tailoring and cover letters.

The one non-negotiable rule, stated in every prompt: the model may REFRAME
and EMPHASIZE what is truly in the resume, but must NEVER invent experience,
skills, employers, dates, or credentials. Tailoring means honest re-emphasis,
not fabrication.
"""

TAILORING_SYSTEM_PROMPT = """You are an expert resume coach helping a candidate adapt their \
resume for one specific job description.

STRICT TRUTHFULNESS RULES — these override everything else:
- Use ONLY facts present in the candidate's resume. Never invent employers, titles, \
dates, projects, metrics, degrees, or certifications.
- You may only suggest surfacing a skill if the resume contains concrete evidence for it; \
always cite that evidence.
- Skills the job wants but the candidate genuinely lacks belong in "honest_gaps", \
never woven into rewrites.
- Rewrites re-order, re-word and emphasize; they never add new claims.

Output ONLY valid JSON, no markdown, no commentary."""


def build_tailoring_prompt(
    resume_summary: str,
    job_title: str,
    company: str | None,
    job_description: str,
    missing_skills: list[str],
    ats_missing_keywords: list[str],
) -> str:
    return f"""Target job: {job_title}{f" at {company}" if company else ""}

Job description:
\"\"\"
{job_description[:4000]}
\"\"\"

Candidate resume (parsed summary):
\"\"\"
{resume_summary}
\"\"\"

Skills the job wants that the matcher flagged as missing: {missing_skills}
ATS keywords not found in the resume: {ats_missing_keywords}

Respond with ONLY this JSON shape:
{{
  "tailored_summary": "2-3 sentence professional summary rewritten to target THIS job, using only true facts",
  "bullet_rewrites": [
    {{"original": "existing resume point", "rewritten": "same fact, re-worded to speak to this JD"}}
  ],
  "surfaceable_skills": [
    {{"skill": "skill the JD wants that the candidate truly has but under-emphasizes", "evidence": "where the resume proves it"}}
  ],
  "ats_keywords_to_add": ["keywords from the JD the candidate can truthfully include"],
  "honest_gaps": [
    {{"skill": "requirement the candidate genuinely lacks", "suggestion": "how to close the gap (course, project...)"}}
  ]
}}"""


COVER_LETTER_SYSTEM_PROMPT = """You write concise, professional cover letters (250-350 words).

STRICT TRUTHFULNESS RULES:
- Ground every claim in the candidate's resume — never invent experience, numbers, or skills.
- Mention the company and role specifically; connect 2-3 real resume facts to the job's needs.
- Confident but honest tone. No clichés ("I am writing to express..."), no flattery padding.
- Output ONLY the letter body text — no JSON, no subject line, no address headers."""


def build_cover_letter_prompt(
    resume_summary: str,
    candidate_name: str | None,
    job_title: str,
    company: str | None,
    job_description: str,
) -> str:
    return f"""Candidate: {candidate_name or "the candidate"}

Candidate resume (parsed summary):
\"\"\"
{resume_summary}
\"\"\"

Target job: {job_title}{f" at {company}" if company else ""}

Job description:
\"\"\"
{job_description[:4000]}
\"\"\"

Write the cover letter now (250-350 words, letter body only, sign off with the candidate's name)."""
