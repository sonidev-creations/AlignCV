import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import httpx
from fastapi import HTTPException
from groq import RateLimitError

from app.main import groq_generate


def reply(payload=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=json.dumps(
            payload or {"summary": "Developer", "fields": {}})))])


class ProviderFallbackTests(unittest.TestCase):
    def test_rate_limit_uses_gemini_then_next_request_returns_to_groq(self):
        groq, gemini, recovered = MagicMock(), MagicMock(), MagicMock()
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
        groq.chat.completions.create.side_effect = RateLimitError("limited", response=response, body={})
        gemini.chat.completions.create.return_value = reply()
        recovered.chat.completions.create.return_value = reply()
        with patch.dict("os.environ", {"GROQ_API_KEY": "groq-test", "GEMINI_API_KEY": "gemini-test"}), \
                patch("app.main.Groq", side_effect=[groq, gemini, recovered]) as factory:
            first = groq_generate("Developer resume", "", "brief", "standard", [])
            second = groq_generate("Developer resume", "", "brief", "standard", [])
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(factory.call_count, 3)
        self.assertIn("googleapis.com", factory.call_args_list[1].kwargs["base_url"])
        self.assertNotIn("base_url", factory.call_args_list[2].kwargs)
        request = gemini.chat.completions.create.call_args.kwargs
        self.assertNotIn("extra_body", request)
        self.assertEqual(request["response_format"]["type"], "json_schema")
        for client in (groq, gemini, recovered):
            client.close.assert_called_once()

    def test_non_rate_limit_does_not_use_backup(self):
        with patch("app.main._provider_generate", side_effect=HTTPException(502, "failed")) as generate:
            with self.assertRaises(HTTPException):
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(generate.call_count, 1)

    def test_no_backup_key_preserves_rate_limit(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}), \
                patch("app.main._provider_generate", side_effect=HTTPException(429, "limited")) as generate:
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(generate.call_count, 1)

    def test_gemini_invalid_output_is_not_accepted(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GEMINI_API_KEY": "test"}), \
                patch("app.main.Groq") as factory:
            response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
            primary, backup = MagicMock(), MagicMock()
            primary.chat.completions.create.side_effect = RateLimitError("limited", response=response, body={})
            backup.chat.completions.create.return_value = reply({"summary": {"invalid": True}})
            factory.side_effect = [primary, backup]
            with self.assertRaises(HTTPException) as caught:
                groq_generate("resume", "", "brief", "standard", [])
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(backup.chat.completions.create.call_count, 3)
