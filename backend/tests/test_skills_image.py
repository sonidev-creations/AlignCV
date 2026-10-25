import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from app.skills_image import SkillsImageRequest, _generate_cached, generate_skills_image


class SkillsImageTests(unittest.TestCase):
    def setUp(self):
        _generate_cached.cache_clear()

    def test_only_known_categories_are_allowed(self):
        with self.assertRaises(ValidationError):
            SkillsImageRequest(categories=[{'category': 'private resume text', 'count': 1}])

    def test_missing_credentials(self):
        with patch.dict(os.environ, {'CLOUDFLARE_ACCOUNT_ID': '', 'CLOUDFLARE_API_TOKEN': ''}):
            with self.assertRaises(HTTPException) as error:
                generate_skills_image(SkillsImageRequest(categories=[{'category': 'Programming', 'count': 2}]))
        self.assertEqual(error.exception.status_code, 503)

    def test_image_is_cached_and_prompt_contains_only_categories(self):
        encoded = base64.b64encode(b'\xff\xd8\xfftest').decode()
        response = MagicMock(status_code=200)
        response.json.return_value = {'success': True, 'result': {'image': encoded}}
        with patch.dict(os.environ, {'CLOUDFLARE_ACCOUNT_ID': 'account123', 'CLOUDFLARE_API_TOKEN': 'secret'}), patch('app.skills_image.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = response
            first = generate_skills_image(SkillsImageRequest(categories=[{'category': 'Programming', 'count': 2}]))
            second = generate_skills_image(SkillsImageRequest(categories=[{'category': 'Programming', 'count': 5}]))
            self.assertEqual(first, second)
            self.assertTrue(first['image_url'].startswith('data:image/jpeg;base64,'))
            post.assert_called_once()
            self.assertIn('Programming', post.call_args.kwargs['json']['prompt'])

    def test_invalid_image_is_not_cached(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'success': True, 'result': {'image': 'invalid'}}
        with patch('app.skills_image.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = response
            with self.assertRaises(HTTPException) as error:
                _generate_cached('account', 'token', ('Programming',))
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(_generate_cached.cache_info().currsize, 0)
