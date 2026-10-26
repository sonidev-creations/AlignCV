import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import httpx
from fastapi import HTTPException
from groq import RateLimitError, APIStatusError

from app.main import groq_generate, compact_document, compact_analysis_schema, request_output_budget


def reply(payload=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=json.dumps(
            payload or {"summary": "Developer", "fields": {}})))])


class ProviderFallbackTests(unittest.TestCase):
    def test_document_compaction_preserves_words_and_section_lines(self):
        self.assertEqual(compact_document("  Jane   Doe\n\n Skills\t Python  SQL\n"),
                         "Jane Doe\nSkills Python SQL")

    def test_compact_schema_preserves_constraints(self):
        schema = compact_analysis_schema()
        self.assertNotIn('"title":', json.dumps(schema))
        self.assertEqual(schema["$defs"]["JobRequirement"]["properties"]["jd_evidence"]["minLength"], 1)

    def test_size_rejection_reduces_output_budget_without_losing_evidence(self):
        client = MagicMock()
        response = httpx.Response(413, request=httpx.Request("POST", "https://api.groq.com"))
        error = APIStatusError("too large", response=response, body={})
        client.chat.completions.create.side_effect = [error, reply()]
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), \
                patch("app.main.Groq", return_value=client):
            groq_generate("FULL RESUME END", "", "brief", "standard", [])
        calls = client.chat.completions.create.call_args_list
        self.assertEqual([call.kwargs["max_tokens"] for call in calls], [3000, 1500])
        for call in calls:
            self.assertIn("FULL RESUME END", call.kwargs["messages"][1]["content"])
            self.assertNotIn('"$defs"', call.kwargs["messages"][1]["content"])

    def test_persistent_size_rejection_stops_without_another_provider(self):
        client = MagicMock()
        response = httpx.Response(413, request=httpx.Request("POST", "https://api.groq.com"))
        client.chat.completions.create.side_effect = APIStatusError("too large", response=response, body={})
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.main.Groq", return_value=client) as factory:
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 413)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        client.close.assert_called_once()

    def test_rate_limit_is_not_retried(self):
        client = MagicMock()
        response = httpx.Response(429, headers={"retry-after": "30"}, request=httpx.Request("POST", "https://api.groq.com"))
        client.chat.completions.create.side_effect = RateLimitError("limited", response=response, body={})
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.main.Groq", return_value=client) as factory:
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.headers["Retry-After"], "30")
        self.assertEqual(factory.call_count, 1)
        client.chat.completions.create.assert_called_once()

    def test_oversized_input_never_reaches_groq(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_REQUEST_TOKEN_BUDGET": "7000"}), patch("app.main.Groq") as factory:
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume " * 10000, "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 413)
        factory.return_value.chat.completions.create.assert_not_called()
        factory.return_value.close.assert_called_once()

    def test_budget_counts_schema_and_multibyte_text(self):
        with patch.dict("os.environ", {"GROQ_REQUEST_TOKEN_BUDGET": "7000"}):
            self.assertEqual(request_output_budget([], {}, 3000), 3000)
            with self.assertRaises(HTTPException):
                request_output_budget([], {"schema": "\u754c" * 6000}, 3000)

    def test_invalid_budget_configuration_is_reported(self):
        for value in ("bad", "-1", "0"):
            with self.subTest(value=value), patch.dict("os.environ", {"GROQ_REQUEST_TOKEN_BUDGET": value}):
                with self.assertRaises(HTTPException) as caught:
                    request_output_budget([], {}, 3000)
                self.assertEqual(caught.exception.status_code, 503)

    def test_truncated_answer_is_discarded_without_wasting_retry_tokens(self):
        client = MagicMock()
        response = reply()
        response.choices[0].finish_reason = "length"
        client.chat.completions.create.return_value = response
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.main.Groq", return_value=client):
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 422)
        client.chat.completions.create.assert_called_once()

    def test_json_fallback_keeps_schema_in_prompt(self):
        client = MagicMock()
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com"))
        client.chat.completions.create.side_effect = [
            APIStatusError("bad json", response=response, body={"error": {"code": "json_validate_failed"}}), reply()]
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.main.Groq", return_value=client):
            groq_generate("resume", "", "brief", "standard", [])
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["response_format"]["type"], "json_object")
        self.assertEqual(request["messages"][1]["content"].count("\nSchema:"), 1)
