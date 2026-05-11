import json
import os
import re
import time

import google.generativeai as genai


class GeminiScorer:
    def __init__(self, kb: dict):
        self.kb = kb
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set.\n"
                "Run: export GEMINI_API_KEY=your_key_here"
            )
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def score(self, card: dict, jd: dict) -> dict:
        """Score a job against the KB. Returns a dict with all sheet columns."""

        # Compact KB for the prompt (keeps tokens low)
        kb_summary = {
            "name": self.kb["profile"]["name"],
            "title": self.kb["profile"]["current_title"],
            "years_exp": self.kb["profile"]["years_of_experience"],
            "location": self.kb["profile"]["current_location"],
            "primary_skills": [s["skill"] for s in self.kb["skills"]["primary"]],
            "secondary_skills": [s["skill"] for s in self.kb["skills"]["secondary"]],
            "target_titles": self.kb["job_preferences"]["target_titles"],
            "preferred_work_type": self.kb["job_preferences"]["work_type"],
            "differentiators": self.kb["differentiators"],
            "top_highlights": [
                {"what": h["what"], "impact": h["impact"]}
                for h in self.kb["experience_highlights"][:4]
            ],
            "strong_fit_signals": self.kb["scoring_hints"]["strong_fit_signals"][:25],
            "weak_fit_signals": self.kb["scoring_hints"]["weak_fit_signals"],
        }

        jd_text = (jd.get("description") or "")[:3500]

        prompt = f"""You are a precise job-fit analyst. Analyze the job posting against the candidate profile below.

CANDIDATE PROFILE:
{json.dumps(kb_summary, indent=2)}

JOB POSTING:
Title:    {card.get("title", "")}
Company:  {card.get("company", "")}
Location: {card.get("location", "")}
Description:
{jd_text}

Return ONLY a valid JSON object — no markdown fences, no explanation, no extra text.

{{
  "score": <integer 1-10 — 8-10=strong fit, 6-7=maybe, 1-5=weak>,
  "reasoning": "<2-3 sentences explaining the score based on skill match and role fit>",
  "why_strong": "<2 sentences on candidate's specific strengths for THIS role>",
  "what_missing": "<1 sentence on any gap, or 'No significant gaps' if strong fit>",
  "connection_note": "<LinkedIn connection note max 280 chars, personalized to this specific role and company, first-person, no emojis>",
  "recruiter_name": <string if recruiter name is visible in the JD, else null>,
  "recruiter_linkedin": <string URL if recruiter LinkedIn is in the JD, else null>,
  "recruiter_email": <string if recruiter email is explicitly in the JD, else null>,
  "company_domain": "<infer the company website domain e.g. razorpay.com — educated guess is fine, else null>",
  "apply_url": "<direct career page URL if mentioned in the JD text, else null>",
  "recruiter_mail_draft": "<concise 120-word cold email to the recruiter about this specific role, professional and personalized>"
}}"""

        for attempt in range(2):
            try:
                response = self.model.generate_content(prompt)
                raw = response.text.strip()

                # Strip accidental markdown fences
                raw = re.sub(r"^```json\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

                result = json.loads(raw)

                # Compute guessed email from recruiter name + company domain
                result["guessed_email"] = self._guess_email(
                    result.get("recruiter_name"),
                    result.get("company_domain"),
                )

                return result

            except json.JSONDecodeError as e:
                print(f"    ⚠️  JSON parse error (attempt {attempt + 1}): {e}")
            except Exception as e:
                print(f"    ⚠️  Gemini error (attempt {attempt + 1}): {e}")

            if attempt == 0:
                time.sleep(3)

        # Fallback — don't crash, just skip to sheet write
        return {
            "score": 0,
            "reasoning": "Scoring failed — Gemini did not return valid JSON.",
            "why_strong": "",
            "what_missing": "",
            "connection_note": "",
            "recruiter_name": None,
            "recruiter_linkedin": None,
            "recruiter_email": None,
            "guessed_email": None,
            "company_domain": None,
            "apply_url": None,
            "recruiter_mail_draft": "",
        }

    # ─────────────────────────────────────────────────────────────
    # Helper
    # ─────────────────────────────────────────────────────────────

    def _guess_email(self, name: str | None, domain: str | None) -> str | None:
        if not name or not domain:
            return None
        parts = name.lower().strip().split()
        if not parts:
            return None
        first = re.sub(r"[^a-z]", "", parts[0])
        if len(parts) >= 2:
            last = re.sub(r"[^a-z]", "", parts[-1])
            return f"{first}.{last}@{domain}"
        return f"{first}@{domain}"
