import base64
import binascii
import os
from functools import lru_cache
from threading import Lock
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field


class SkillCategory(BaseModel):
    category: Literal['AI & LLM', 'Programming', 'Web & APIs', 'Data & Databases', 'Cloud & Tools', 'Other']
    count: int = Field(ge=1, le=1000)


class SkillsImageRequest(BaseModel):
    categories: list[SkillCategory] = Field(min_length=1, max_length=6)


_generation_lock = Lock()


def generate_skills_image(request: SkillsImageRequest) -> dict[str, str]:
    account = os.getenv('CLOUDFLARE_ACCOUNT_ID', '').strip()
    token = os.getenv('CLOUDFLARE_API_TOKEN', '').strip()
    if not account or not token:
        raise HTTPException(503, 'Skills artwork is not configured yet. Add the Cloudflare credentials to backend/.env.')
    if not account.isalnum():
        raise HTTPException(503, 'Check the Cloudflare Account ID in backend/.env.')
    categories = tuple(sorted({item.category for item in request.categories}))
    with _generation_lock:
        return _generate_cached(account, token, categories)


@lru_cache(maxsize=16)
def _generate_cached(account: str, token: str, categories: tuple[str, ...]) -> dict[str, str]:
    prompt = (
        'Create a polished editorial illustration for a professional resume skills report. '
        'White background, navy blue and teal accents, clean isometric objects, balanced composition, '
        'crisp modern shapes with generous whitespace. Represent these skill themes using visual metaphors: '
        + ', '.join(categories)
        + '. No text, letters, numbers, charts, percentages, logos or people. Decorative artwork only.'
    )
    url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell'
    try:
        with httpx.Client(timeout=60.0, follow_redirects=False) as client:
            response = client.post(url, headers={'Authorization': f'Bearer {token}'}, json={'prompt': prompt, 'steps': 4})
        if response.status_code == 429:
            raise HTTPException(429, 'Image generation is busy or its quota is reached. Please try again later.')
        if response.status_code in {401, 403}:
            raise HTTPException(503, 'Check the Cloudflare token and its Workers AI permissions.')
        response.raise_for_status()
        payload = response.json()
        result = payload.get('result') if isinstance(payload, dict) and payload.get('success') else None
        encoded = result.get('image') if isinstance(result, dict) else None
        if not isinstance(encoded, str) or len(encoded) > 12_000_000:
            raise ValueError('Invalid image response')
        raw = base64.b64decode(encoded, validate=True)
        if not raw.startswith(b'\xff\xd8\xff'):
            raise ValueError('Expected a JPEG image')
    except httpx.TimeoutException as exc:
        raise HTTPException(504, 'Image generation took too long. Your report is still available; try again shortly.') from exc
    except (httpx.HTTPError, ValueError, binascii.Error) as exc:
        raise HTTPException(502, 'Could not generate skills artwork. Your report is still available.') from exc
    return {'image_url': f'data:image/jpeg;base64,{encoded}', 'alt': 'AI-generated illustration of ' + ', '.join(categories)}
