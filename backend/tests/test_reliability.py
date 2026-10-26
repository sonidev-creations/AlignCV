import time
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from groq import RateLimitError

from app.main import analyze_document, evidence_matches, groq_generate, job_match, neutral_language, verify_evidence
from app.schemas import AnalysisResult, JobRequirement


class ReliabilityTests(unittest.TestCase):
    def test_model_cannot_drop_second_work_role(self):
        source = ("EXPERIENCE\nEngineer | Alpha | 2024\nBuilt Python APIs\n"
                  "Developer | Beta | 2023\nBuilt React screens\nEDUCATION\nBachelor degree")
        result = AnalysisResult(summary="", fields={"experience": {
            "value": ["Engineer | Alpha | 2024"], "evidence": ["Engineer | Alpha | 2024"]}})
        field = verify_evidence(result, source).fields.experience
        self.assertEqual(len(field.value), 2)
        self.assertIn("Developer | Beta", field.value[1])

    def test_preferred_section_overrides_incorrect_model_priority(self):
        row = JobRequirement(requirement="Docker familiarity", jd_evidence="Docker familiarity",
                             category="skills", essential=True, status="met", evidence=["Docker"], reason="Listed")
        match = job_match("Docker", "Required:\nPython\nPreferred:\nDocker familiarity", [row])
        self.assertFalse(match["requirements"][0]["essential"])

    def test_model_retries_omitted_job_comparison(self):
        import json
        from types import SimpleNamespace
        row = JobRequirement(requirement="Python", jd_evidence="Python", category="skills",
                             status="met", evidence=["Python"], reason="Listed")
        def response(rows):
            payload = {"summary": "Developer", "fields": {}, "job_requirements": rows}
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(payload)))])
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.Groq") as client:
            create = client.return_value.chat.completions.create
            create.side_effect = [response([]), response([row.model_dump()])]
            result = groq_generate("Python developer", "Python", "brief", "standard", [])
        self.assertEqual(len(result.job_requirements), 1)
        self.assertEqual(create.call_count, 2)

    def test_summary_experience_word_does_not_hide_actual_work_section(self):
        source = ("SUMMARY\nDeveloper with experience in Python.\nPROJECTS\nPython demo\n"
                  "WORK EXPERIENCE:\nEngineer | Example Ltd | 2024 - 2025\nBuilt Python services\n"
                  "EDUCATION\nBachelor degree")
        result = verify_evidence(AnalysisResult(summary="", fields={}), source)
        field = result.fields.experience
        self.assertEqual(field.status, "supported")
        self.assertIn("Engineer | Example Ltd", field.value[0])
        self.assertNotIn("Bachelor", field.value[0])
        self.assertNotIn("Python demo", field.value[0])
        requirement = JobRequirement(requirement="Python experience", jd_evidence="Python experience",
                                     category="experience", status="missing", reason="No quote")
        match = job_match(source, "Python experience", [requirement])
        self.assertEqual(match["categories"][0]["score"], 40)

    def test_projects_do_not_become_employment(self):
        source = "SUMMARY\nStudent with experience building Python demos.\nPROJECTS\nEngineer dashboard built in 2025"
        result = verify_evidence(AnalysisResult(summary="", fields={}), source)
        self.assertIsNone(result.fields.experience.value)

    def test_explicit_no_experience_is_not_recovered(self):
        source = "EXPERIENCE\nNo prior work experience. Seeking an engineer internship in 2026."
        self.assertIsNone(verify_evidence(AnalysisResult(summary="", fields={}), source).fields.experience.value)

    def test_missing_comparison_returns_unavailable_instead_of_false_zero(self):
        with patch("app.main.groq_generate", return_value=AnalysisResult(summary="Developer", fields={})):
            report = analyze_document("resume.txt", b"Developer building Python applications and APIs.",
                                      "brief", "standard", "[]", "Python developer required", False, True,
                                      time.perf_counter())
        self.assertIsNone(report["job_match"]["score"])
        self.assertEqual(report["analysis_version"], "2")

    def test_skill_quote_cannot_support_invented_skills(self):
        result = AnalysisResult(summary="", fields={"skills": {
            "value": ["Python", "Kubernetes"], "evidence": ["Python"]}})
        self.assertEqual(verify_evidence(result, "Skills: Python").fields.skills.value, ["Python"])

    def test_languages_with_suffixes_are_not_interchangeable(self):
        self.assertFalse(evidence_matches("Skills: C", "C++"))
        self.assertFalse(evidence_matches("Skills: C#", "C++"))
        self.assertFalse(evidence_matches("Skills: C++", "C"))
        self.assertTrue(evidence_matches("Skills: C++", "C++"))

    def test_keyword_recovery_cannot_prove_five_years(self):
        requirement = JobRequirement(requirement="Five years Python experience", jd_evidence="Five years Python experience",
                                     category="experience", status="missing", reason="No quote")
        match = job_match("EXPERIENCE\nIntern | Example | 2025\nPython", "Five years Python experience", [requirement])
        self.assertEqual(match["requirements"][0]["status"], "partial")

    def test_neutral_generated_language(self):
        text = neutral_language("She uses Python. Her work shows his skills; he built it.")
        self.assertNotRegex(text.lower(), r"\b(?:he|she|his|her)\b")

    def test_rate_limits_remain_explicit_errors_with_retry_header(self):
        response = httpx.Response(429, headers={"retry-after": "30"},
                                  request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.Groq") as client:
            client.return_value.chat.completions.create.side_effect = RateLimitError("Limit", response=response, body={})
            with self.assertRaises(HTTPException) as raised:
                groq_generate("Python", "", "brief", "standard", [])
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.headers["Retry-After"], "30")
