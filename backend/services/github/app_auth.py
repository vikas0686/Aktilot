"""
GitHub App authentication: signs the short-lived app JWT and mints/caches
per-installation access tokens used by services.github.client.

Two token types are involved:
  - App JWT (~10 min, RS256-signed with the App's private key) — authenticates
    as the App itself, only usable against the /app/* endpoints.
  - Installation access token (~1 hr) — minted from the App JWT, used for all
    actual data calls (repos, contents, issues) scoped to what the
    installation was granted.
"""

import time
from datetime import datetime, timezone

import httpx
import jwt

from config import settings

_GITHUB_API = "https://api.github.com"

# installation_id -> (token, expires_at epoch seconds)
_installation_token_cache: dict[int, tuple[str, float]] = {}

_TOKEN_REFRESH_BUFFER_SECONDS = 5 * 60


class GithubAppNotConfiguredError(Exception):
    pass


def _app_jwt() -> str:
    if not settings.github_app_id or not settings.github_app_private_key:
        raise GithubAppNotConfiguredError(
            "GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY are not configured"
        )
    now = int(time.time())
    payload = {
        "iat": now - 60,  # allow for clock drift
        "exp": now + 9 * 60,
        "iss": settings.github_app_id,
    }
    # .env stores the PEM with literal "\n" sequences (real newlines don't survive
    # single-line env files); un-escape them so pyjwt gets a valid multi-line PEM.
    # A no-op if the key already has real newlines (e.g. injected via a secrets file).
    private_key = settings.github_app_private_key.replace("\\n", "\n")
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    cached = _installation_token_cache.get(installation_id)
    if cached and cached[1] - _TOKEN_REFRESH_BUFFER_SECONDS > time.time():
        return cached[0]

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {_app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    token: str = data["token"]
    # expires_at is an ISO8601 UTC string; store as epoch for cheap comparison
    expires_at = (
        datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    _installation_token_cache[installation_id] = (token, expires_at)
    return token


def invalidate_installation_token(installation_id: int) -> None:
    _installation_token_cache.pop(installation_id, None)
