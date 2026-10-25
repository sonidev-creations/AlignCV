import unittest
import asyncio
import threading
from io import BytesIO
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import UploadFile
from app.main import analyze, chunk_text, completeness, evidence_matches, extract_text, fallback_job_requirements, job_match, verify_evidence, skill_categories
from app.schemas import AnalysisResult, JobRequirement
from app.main import groq_generate, evidence_coverage


class LogicTests(unittest.TestCase):
    def test_analysis_does_not_block_other_async_requests(self):
        started = threading.Event()
        release = threading.Event()

        def generate(*args):
            started.set()
            release.wait(timeout=5)
            return AnalysisResult(summary="Summary", fields={})

        async def check():
            task = asyncio.create_task(analyze(
                UploadFile(filename="resume.txt", file=BytesIO(b"Python developer with experience building web applications.")),
                "brief", "standard", "[]", "", False,
            ))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                # The event loop can serve another coroutine before Groq finishes.
                self.assertFalse(task.done())
            finally:
                release.set()
                await task

        with patch("app.main.groq_generate", side_effect=generate):
            asyncio.run(check())

    def test_disabled_rag_skips_retrieval_work(self):
        with patch("app.main.chunk_text") as chunk, patch("app.main.retrieve") as retrieve, patch(
            "app.main.groq_generate", return_value=AnalysisResult(summary="Summary", fields={})
        ):
            result = asyncio.run(analyze(
                UploadFile(filename="resume.txt", file=BytesIO(b"Python developer with experience building web applications.")),
                "brief", "standard", "[]", "", False,
            ))
            chunk.assert_not_called()
            retrieve.assert_not_called()
            self.assertEqual(result["retrieval_method"], "full_context")

    def test_invalid_chunk_settings_are_rejected(self):
        for size, overlap in [(0, 0), (10, 10), (10, -1)]:
            with self.assertRaises(ValueError):
                chunk_text("Resume text", size=size, overlap=overlap)

    def test_summary_overlap_combines_verified_excerpts(self):
        result = AnalysisResult(summary="Python React developer studying information technology.", fields={
            "skills": {"value": ["Python", "React"], "evidence": ["Python", "React"]},
            "education": {"value": "Information Technology", "evidence": ["information technology"]}})
        coverage = evidence_coverage(result, "Python React information technology")
        self.assertGreater(coverage['score'], 50)
        self.assertEqual(len(coverage['sentences'][0]['excerpts']), 3)

    def test_long_summary_gets_partial_credit_across_short_quotes(self):
        result = AnalysisResult(summary="Python React FastAPI SQL AWS Docker developer building scalable platforms and delivering reliable products.", fields={
            "skills": {"value": ["Python", "React", "FastAPI", "SQL", "AWS"],
                       "evidence": ["Python", "React", "FastAPI", "SQL", "AWS"]}})
        coverage = evidence_coverage(result, "Python React FastAPI SQL AWS")
        self.assertGreater(coverage['score'], 0)
        self.assertLess(coverage['score'], 100)
        self.assertEqual(coverage['matched_terms'], 5)

    def test_summary_overlap_does_not_credit_unverified_or_unrelated_text(self):
        result = AnalysisResult(summary="Astronaut researching lunar geology.", fields={
            "skills": {"value": "Python", "evidence": ["Astronaut researching lunar geology.", "Python"]}})
        coverage = evidence_coverage(result, "Python web development")
        self.assertEqual(coverage['score'], 0)
        self.assertEqual(coverage['sentences'][0]['excerpts'], [])

    def test_empty_summary_has_no_measurable_overlap(self):
        self.assertIsNone(evidence_coverage(AnalysisResult(summary="", fields={}), "")['score'])

    def test_skill_visual_counts_every_unique_skill_once(self):
        skills = ["Python", "Python", "LLMs", "LangChain", "React.js", "ChromaDB", "Unknown tool"]
        counts = {item['category']: item['count'] for item in skill_categories(skills)}
        self.assertEqual(sum(counts.values()), 6)
        self.assertEqual(counts['AI & LLM'], 2)
        self.assertEqual(counts['Other'], 1)

    def test_invalid_model_output_is_retried(self):
        def response(content):
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.Groq") as client:
            create = client.return_value.chat.completions.create
            create.side_effect = [response('{"summary":"Text","fields":{"education":{"value":{"degree":"B.Tech"}}}}'), response('{"summary":"Text","fields":{"education":{"value":"B.Tech"}}}')]
            result = groq_generate("B.Tech", "", "brief", "standard", [])
            self.assertEqual(result.fields.education.value, "B.Tech")
            self.assertEqual(create.call_count, 2)

    def test_full_resume_reaches_model_even_when_retrieval_omits_sections(self):
        source = "NAME AT START\n" + "Project details. " * 1000 + "\nEDUCATION AT END"
        result = AnalysisResult(summary="Summary", fields={})
        with patch("app.main.retrieve", return_value=(["Project details."], "lexical_fallback")), patch("app.main.groq_generate", return_value=result) as generate:
            asyncio.run(analyze(UploadFile(filename="resume.txt", file=BytesIO(source.encode())), "brief", "standard", "[]", "", True))
            self.assertIn(source, generate.call_args.args[0])

    def test_pdf_whitespace_does_not_remove_valid_evidence(self):
        result = AnalysisResult.model_validate({"summary": "Summary", "fields": {"education": {"value": "B.Tech Information Technology", "evidence": ["B.Tech Information Technology"]}}})
        result = verify_evidence(result, "B.Tech\n  Information\u00a0Technology")
        self.assertEqual(result.fields.education.status, "supported")

    def test_pdf_formatting_variations_keep_valid_evidence(self):
        source = "Jane\nExample\n j ane@example.com\nSoftware-\ndeveloper\nReact.js"
        self.assertTrue(evidence_matches(source, "Jane Example"))
        self.assertTrue(evidence_matches(source, "jane@example.com"))
        self.assertTrue(evidence_matches(source, "Software-developer"))
        self.assertTrue(evidence_matches(source, "React.js"))
        self.assertFalse(evidence_matches("Firstname only", "name"))
        result = AnalysisResult.model_validate({"summary": "Jane is a software developer.", "fields": {
            "name": {"value": "Jane Example", "evidence": ["Jane Example"]},
            "email": {"value": "jane@example.com", "evidence": ["jane@example.com"]},
            "experience": {"value": "Software-developer", "evidence": ["Software-developer"]}}})
        result = verify_evidence(result, source)
        self.assertEqual(result.fields.name.status, "supported")
        self.assertEqual(result.fields.email.status, "supported")
        self.assertEqual(result.fields.experience.status, "supported")

    def test_different_resume_formats_are_verified_independently(self):
        first = AnalysisResult(summary="First", fields={"name": {"value": "Asha Rao", "evidence": ["Asha Rao"]}})
        second = AnalysisResult(summary="Second", fields={"name": {"value": "Ben Lee", "evidence": ["Ben Lee"]}})
        first = verify_evidence(first, "Asha Rao\nPython developer")
        second = verify_evidence(second, "Ben Lee\nJava developer")
        self.assertEqual(first.fields.name.status, "supported")
        self.assertEqual(second.fields.name.status, "supported")
        self.assertIsNone(verify_evidence(first, "Ben Lee\nJava developer").fields.name.value)

    def test_grouped_skills_are_counted_individually(self):
        counts = {x["category"]: x["count"] for x in skill_categories("AI & ML: RAG, NLP; Programming: Python, JavaScript; Web: Flask, React")}
        self.assertEqual(counts, {"AI & LLM": 2, "Programming": 2, "Web & APIs": 2})

    def test_chunking_covers_text(self):
        text = ("Python FastAPI experience. " * 100).strip()
        chunks = chunk_text(text, size=200, overlap=30)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))

    def test_text_extraction_rejects_empty_or_unreadable(self):
        with self.assertRaises(Exception):
            extract_text("empty.txt", b"")
        self.assertIn("resume", extract_text("resume.txt", b"A readable resume with enough content for testing." ).lower())

    def test_unverifiable_field_is_removed(self):
        result = AnalysisResult.model_validate({"summary":"A short summary.","fields":{"name":{"value":"Invented Person","evidence":["not in the resume"],"status":"supported"}}})
        result = verify_evidence(result, "Only real source text.")
        self.assertIsNone(result.fields.name.value)
        self.assertEqual(result.fields.name.status, "uncertain")

    def test_completeness_and_job_match(self):
        result = AnalysisResult.model_validate({"summary":"Summary.","fields":{"email":{"value":"a@b.com","evidence":["a@b.com"],"status":"supported"},"skills":{"value":["Python","FastAPI"],"evidence":["Python FastAPI"],"status":"supported"}}})
        result = verify_evidence(result,"a@b.com Python FastAPI")
        self.assertEqual(completeness(result)["score"],40)
        match = job_match("Python FastAPI", "Looking for Python and FastAPI skills", [JobRequirement(requirement="Python and FastAPI", jd_evidence="Python and FastAPI skills", category="skills", status="met", evidence=["Python FastAPI"], reason="Both tools listed.")])
        self.assertEqual(match["score"],100)

    def test_shared_skills_do_not_hide_missing_essential_experience(self):
        requirements = [JobRequirement(requirement="Python", jd_evidence="Python", category="skills", status="met", evidence=["Python"], reason="Listed.")]
        requirements += [JobRequirement(requirement="Five years nursing experience", jd_evidence="Five years nursing experience", category="experience", status="missing", reason="Unrelated resume.")]
        match = job_match("Python web developer", "Python. Five years nursing experience", requirements)
        self.assertLessEqual(match["score"], 59)
        self.assertIn("Five years nursing experience", match["missing"])

    def test_unverified_resume_and_jd_quotes_cannot_inflate_match(self):
        r = JobRequirement(requirement="AWS certification", jd_evidence="AWS certification", category="certifications", status="met", evidence=["AWS certified"], reason="Certified.")
        self.assertEqual(job_match("AWS skills", "AWS certification required", [r])["score"], 0)
        self.assertIsNone(job_match("AWS certified", "Unrelated description", [r])["score"])

    def test_projects_and_certifications_count_with_partial_credit(self):
        rows = [JobRequirement(requirement="Deployed project", jd_evidence="Deployed project", category="projects", status="partial", evidence=["Built app"], reason="Deployment not shown."),
                JobRequirement(requirement="Certification", jd_evidence="Certification", category="certifications", status="met", evidence=["Certified"], reason="Present.")]
        match = job_match("Built app. Certified", "Deployed project. Certification", rows)
        self.assertEqual(match["score"], 70)
        self.assertEqual(len(match["categories"]), 2)
        self.assertIsNone(job_match("resume", ""))

    def test_job_match_accepts_formatted_job_description_evidence(self):
        requirement = JobRequirement(requirement="FastAPI experience", jd_evidence="FastAPI\nexperience", category="experience", status="met", evidence=["FastAPI\nservices"], reason="Relevant API work.")
        match = job_match("Built FastAPI\nservices", "Required: FastAPI experience", [requirement])
        self.assertEqual(match["score"], 100)

    def test_job_match_categories_use_stable_display_order(self):
        rows = [
            JobRequirement(requirement="Responsibilities", jd_evidence="Responsibilities", category="responsibilities", status="met", evidence=["Responsibilities"], reason="Present."),
            JobRequirement(requirement="Python", jd_evidence="Python", category="skills", status="met", evidence=["Python"], reason="Present."),
            JobRequirement(requirement="Experience", jd_evidence="Experience", category="experience", status="met", evidence=["Experience"], reason="Present."),
        ]
        categories = job_match("Python Experience Responsibilities", "Python Experience Responsibilities", rows)["categories"]
        self.assertEqual([item["category"] for item in categories], ["skills", "experience", "responsibilities"])

    def test_skill_match_recovers_verifiable_source_lines_when_model_quote_is_missing(self):
        requirement = JobRequirement(
            requirement="Python, FastAPI or Flask, and REST APIs",
            jd_evidence="Python, FastAPI or Flask, and REST APIs",
            category="skills", status="missing", evidence=[], reason="No evidence returned.",
        )
        match = job_match(
            "Languages: Python\nBackend: FastAPI\nServices: REST APIs",
            "Required: Python, FastAPI or Flask, and REST APIs",
            [requirement],
        )
        row = match["requirements"][0]
        self.assertEqual(row["status"], "met")
        self.assertEqual(row["evidence"], ["Languages: Python", "Backend: FastAPI", "Services: REST APIs"])
        self.assertIn("Matched 3 of 3", row["reason"])

    def test_experience_match_recovers_verifiable_work_lines_when_model_quote_is_missing(self):
        requirement = JobRequirement(
            requirement="Practical experience building interfaces with React and JavaScript",
            jd_evidence="Practical experience building interfaces with React and JavaScript",
            category="experience", status="missing", evidence=[], reason="No evidence returned.",
        )
        match = job_match(
            "EXPERIENCE\nSOFTWARE DEVELOPER INTERN | Northstar\nBuilt React features with JavaScript\nEDUCATION\nBachelor of Engineering",
            "Required: Practical experience building interfaces with React and JavaScript",
            [requirement],
        )
        row = match["requirements"][0]
        self.assertEqual(row["status"], "partial")
        self.assertIn("Built React features with JavaScript", row["evidence"])

    def test_job_match_reports_missing_job_description(self):
        self.assertIsNone(job_match("A valid resume with text", ""))

    def test_fallback_job_requirements_preserve_supplied_jd_when_model_returns_none(self):
        rows = fallback_job_requirements("Required:\n- Python and FastAPI experience\nPreferred:\n- Docker familiarity")
        self.assertEqual([row.requirement for row in rows], ["Python and FastAPI experience", "Docker familiarity"])
        self.assertTrue(rows[0].essential)
        self.assertFalse(rows[1].essential)

    def test_empty_focus_defaults_to_all_sections(self):
        from app.main import normalize_focus
        self.assertEqual(normalize_focus([]), ["skills", "education", "experience", "projects", "contact"])
        self.assertEqual(normalize_focus(None), normalize_focus([]))
        self.assertEqual(normalize_focus(["skills"]), ["skills"])
        for focus in ("[]", "null", "{}", "invalid"):
            with patch("app.main.groq_generate", return_value=AnalysisResult(summary="Summary", fields={})) as generate:
                asyncio.run(analyze(UploadFile(filename="resume.txt", file=BytesIO(b"Python developer building web applications and APIs.")), "brief", "standard", focus, "", False))
                self.assertEqual(generate.call_args.args[4], normalize_focus([]))

    def test_groq_json_rejection_recovers_automatically(self):
        import httpx
        from groq import BadRequestError
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        rejection = BadRequestError("Failed to generate JSON", response=response, body={"error": {"code": "json_validate_failed"}})
        valid = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"summary":"Text","fields":{}}'))])
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.Groq") as client:
            create = client.return_value.chat.completions.create
            create.side_effect = [rejection, valid]
            self.assertEqual(groq_generate("Python developer", "", "brief", "standard", []).summary, "Text")
            self.assertEqual(create.call_count, 2)

    def test_unrelated_groq_400_is_not_retried(self):
        import httpx
        from groq import BadRequestError
        from fastapi import HTTPException
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        rejection = BadRequestError("Invalid model", response=response, body={"error": {"message": "Invalid model"}})
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.Groq") as client:
            client.return_value.chat.completions.create.side_effect = rejection
            with self.assertRaises(HTTPException):
                groq_generate("Python", "", "brief", "standard", [])
            self.assertEqual(client.return_value.chat.completions.create.call_count, 1)

    def test_generation_uses_installed_sdk_compatible_arguments(self):
        import json
        import httpx
        from groq import Groq
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "test-completion", "object": "chat.completion", "created": 0,
                "model": "openai/gpt-oss-20b",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": '{"summary":"Python developer","fields":{}}'}}]})

        client = Groq(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.GROQ_MODEL", "openai/gpt-oss-20b"), patch("app.main.Groq", return_value=client):
            result = groq_generate("Python developer", "", "brief", "standard", [])
        self.assertEqual(result.summary, "Python developer")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["reasoning_effort"], "low")
        self.assertEqual(requests[0]["response_format"]["type"], "json_schema")

    def test_empty_extracted_values_are_null(self):
        for value in ("", "  ", [], [" "]):
            result = AnalysisResult(summary="Summary", fields={"skills": {"value": value, "evidence": ["Python"]}})
            result = verify_evidence(result, "Python")
            self.assertIsNone(result.fields.skills.value)
            self.assertEqual(result.fields.skills.status, "missing")
            self.assertEqual(completeness(result)["score"], 0)

    def test_pdf_and_sample_documents_are_readable(self):
        import fitz
        from app.main import list_samples, get_sample
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72,72), "Sample Candidate: Python developer with web application experience.")
            raw = pdf.tobytes()
        self.assertIn("Sample Candidate", extract_text("resume.pdf", raw))
        self.assertEqual([sample["name"] for sample in list_samples()], ["sample_software_developer_resume.pdf"])
        for sample in list_samples():
            self.assertGreater(len(get_sample(sample["name"])["text"]), 30)

    def test_api_preserves_preferences_and_missing_fields(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with patch("app.main.groq_generate", return_value=AnalysisResult(summary="- Python developer\n- Builds APIs", fields={})) as generate:
            response = TestClient(app).post("/api/analyze", files={"file": ("resume.txt", b"Python developer with experience building web applications.", "text/plain")}, data={"summary_style": "bullets", "analysis_level": "detailed", "focus_areas": "[]", "use_rag": "false"})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["summary_style"], "bullets")
        self.assertEqual(report["analysis_level"], "detailed")
        self.assertEqual(len(report["focus_areas"]), 5)
        for field in report["fields"].values():
            self.assertIsNone(field["value"])
        self.assertEqual(generate.call_args.args[2:4], ("bullets", "detailed"))

    def test_ats_readability_reports_observable_checks(self):
        from app.main import ats_readability
        source = "Jane Example\njane@example.com\nSkills\nPython\nEducation\nBSc Computer Science\nWork Experience\nDeveloper"
        result = verify_evidence(AnalysisResult(summary="Summary", fields={
            "name": {"value": "Jane Example", "evidence": ["Jane Example"]},
            "email": {"value": "jane@example.com", "evidence": ["jane@example.com"]}}), source)
        review = ats_readability(source, result)
        self.assertEqual(review["status"], "Basic checks passed")
        self.assertEqual(review["passed"], review["total"])
        self.assertEqual(review["text_preview"], source)
        self.assertNotIn("score", review)

    def test_ats_readability_does_not_pass_missing_contact_or_headings(self):
        from app.main import ats_readability
        review = ats_readability("Python developer \ufffd", AnalysisResult(summary="Summary", fields={}))
        checks = {check["label"]: check["status"] for check in review["checks"]}
        self.assertEqual(review["status"], "Needs review")
        for label in ("Name", "Email address", "Skills heading", "Education heading", "Experience heading", "Text characters"):
            self.assertEqual(checks[label], "review")

    def test_extraction_schema_rejects_invalid_status(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            AnalysisResult(summary="Summary", fields={"name": {"status": "invented"}})

    def test_completeness_distinguishes_missing_and_uncertain(self):
        result = AnalysisResult(summary="Summary", fields={
            "name": {"value": "Jane", "evidence": ["Jane"], "status": "supported"},
            "email": {"value": None, "status": "uncertain"},
            "skills": {"value": ["Python"], "evidence": ["Python"], "status": "supported"},
            "experience": {"value": "Invented role", "evidence": ["Not in source"], "status": "supported"}})
        result = verify_evidence(result, "Jane Python")
        report = completeness(result)
        self.assertEqual(report["score"], 40)
        self.assertEqual(report["missing"], ["education"])
        self.assertEqual(report["uncertain"], ["email", "experience"])
        self.assertEqual(report["status"], "Needs review")
        self.assertIsNone(result.fields.experience.value)
        self.assertIn("No education data", next(c["message"] for c in report["checks"] if c["field"] == "education"))

    def test_completeness_all_missing_and_all_verified(self):
        missing = completeness(AnalysisResult(summary="Summary", fields={}))
        self.assertEqual(missing["score"], 0)
        self.assertEqual(len(missing["missing"]), 5)
        self.assertTrue(all("No " in check["message"] for check in missing["checks"]))
        fields = {key: {"value": "Present", "evidence": ["Present"], "status": "supported"} for key in ("name", "email", "skills", "education", "experience")}
        full = completeness(verify_evidence(AnalysisResult(summary="Summary", fields=fields), "Present"))
        self.assertEqual(full["score"], 100)
        self.assertEqual(full["status"], "Complete")
        self.assertEqual(full["missing"], [])
        self.assertEqual(full["uncertain"], [])

    def test_sample_pdf_and_job_description_endpoints(self):
        import base64
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        sample = client.get("/api/samples/sample_software_developer_resume.pdf")
        self.assertEqual(sample.status_code, 200)
        payload = sample.json()
        self.assertEqual(payload["media_type"], "application/pdf")
        self.assertTrue(base64.b64decode(payload["content_base64"]).startswith(b"%PDF"))
        self.assertIn("AARAV MENON", payload["text"])
        self.assertIn("React", client.get("/api/sample-job-description").json()["text"])
        self.assertEqual(client.get("/api/samples/sample_ai_engineer_resume.txt").status_code, 404)

    def test_system_status_checks_provider_without_exposing_secrets(self):
        import httpx
        import json
        from app.main import system_status
        reply = httpx.Response(200, json={"data": [{"id": "test-model"}]}, headers={"x-ratelimit-remaining-tokens": "1234"})
        with patch.dict("os.environ", {"GROQ_API_KEY": "private-test-key", "CLOUDFLARE_API_TOKEN": "private-cloud-token"}), patch("app.main.GROQ_MODEL", "test-model"), patch("app.main.httpx.Client") as client:
            client.return_value.__enter__.return_value.get.return_value = reply
            status = system_status()
        self.assertEqual(status["groq"], "Connected")
        self.assertEqual(status["limits"]["Tokens remaining"], 1234)
        self.assertNotIn("private-test-key", json.dumps(status))
        self.assertNotIn("private-cloud-token", json.dumps(status))

    def test_system_status_handles_missing_key_and_connection_failure(self):
        import httpx
        from app.main import system_status
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}), patch("app.main.httpx.Client") as client:
            self.assertEqual(system_status()["groq"], "Not configured")
            client.assert_not_called()
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch("app.main.httpx.Client") as client:
            client.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("Network unavailable")
            status = system_status()
            self.assertEqual(status["backend"], "Connected")
            self.assertEqual(status["groq"], "Could not connect")
            self.assertEqual(status["limits"], {})


if __name__ == "__main__":
    unittest.main()
