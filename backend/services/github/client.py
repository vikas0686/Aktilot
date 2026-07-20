"""
Thin async GitHub REST API client used by the GitHub connector's Temporal
activities. Callers pass an installation access token (from
services.github.app_auth.get_installation_token) for all data calls; app-level
calls (uninstall) sign their own app JWT.
"""

import base64
import re

import httpx

from services.github.app_auth import _app_jwt

_GITHUB_API = "https://api.github.com"
_API_VERSION = "2022-11-28"
_TIMEOUT = httpx.Timeout(30.0)


class GithubAuthError(Exception):
    pass


class GithubNotFoundError(Exception):
    pass


class GithubRateLimitError(Exception):
    pass


class GithubServiceError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    if resp.status_code == 401:
        raise GithubAuthError(f"GitHub authentication failed: {resp.text}")
    if resp.status_code == 404:
        raise GithubNotFoundError(f"GitHub resource not found: {resp.request.url}")
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        raise GithubRateLimitError(
            f"GitHub rate limit exhausted, resets at "
            f"{resp.headers.get('x-ratelimit-reset')}"
        )
    raise GithubServiceError(
        f"GitHub API error {resp.status_code}: {resp.text}",
        status_code=resp.status_code,
    )


_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


async def _paginate(
    http: httpx.AsyncClient, url: str, headers: dict[str, str], params: dict | None = None
) -> list[dict]:
    items: list[dict] = []
    next_url: str | None = url
    next_params = params
    while next_url:
        resp = await http.get(next_url, headers=headers, params=next_params)
        _raise_for_status(resp)
        items.extend(resp.json())
        next_params = None  # subsequent requests use the full URL from Link
        link = resp.headers.get("link", "")
        match = _LINK_NEXT_RE.search(link)
        next_url = match.group(1) if match else None
    return items


async def get_installation(installation_id: int) -> dict:
    """App-JWT authenticated — used right after the install callback to learn
    which account (org/user) the installation belongs to."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        resp = await http.get(
            f"{_GITHUB_API}/app/installations/{installation_id}",
            headers={
                "Authorization": f"Bearer {_app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
            },
        )
        _raise_for_status(resp)
        return resp.json()


async def list_installation_repos(token: str) -> list[dict]:
    """Returns [{full_name, default_branch, private}, ...] the installation can access."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        headers = _headers(token)
        repos: list[dict] = []
        page = 1
        while True:
            resp = await http.get(
                f"{_GITHUB_API}/installation/repositories",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            _raise_for_status(resp)
            data = resp.json()
            batch = data.get("repositories", [])
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return [
        {
            "full_name": r["full_name"],
            "default_branch": r["default_branch"],
            "private": r["private"],
        }
        for r in repos
    ]


async def get_tree(token: str, repo_full_name: str, branch: str) -> list[dict]:
    """Returns the full recursive file tree: [{path, sha, size, type}, ...] (blobs only)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        resp = await http.get(
            f"{_GITHUB_API}/repos/{repo_full_name}/git/trees/{branch}",
            headers=_headers(token),
            params={"recursive": "1"},
        )
        _raise_for_status(resp)
        data = resp.json()
    if data.get("truncated"):
        # Repo tree too large for a single recursive call — still index what we got
        # rather than fail the whole sync.
        pass
    return [item for item in data.get("tree", []) if item.get("type") == "blob"]


async def get_blob(token: str, repo_full_name: str, sha: str) -> str:
    """Fetches and decodes a blob's text content."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        resp = await http.get(
            f"{_GITHUB_API}/repos/{repo_full_name}/git/blobs/{sha}",
            headers=_headers(token),
        )
        _raise_for_status(resp)
        data = resp.json()
    content = base64.b64decode(data["content"])
    return content.decode("utf-8", errors="replace")


async def list_issues(token: str, repo_full_name: str) -> list[dict]:
    """Returns all issues (state=all), excluding pull requests."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        items = await _paginate(
            http,
            f"{_GITHUB_API}/repos/{repo_full_name}/issues",
            _headers(token),
            params={"state": "all", "per_page": 100},
        )
    return [item for item in items if "pull_request" not in item]


async def list_issue_comments(
    token: str, repo_full_name: str, issue_number: int
) -> list[dict]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        return await _paginate(
            http,
            f"{_GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/comments",
            _headers(token),
            params={"per_page": 100},
        )


async def uninstall_app(installation_id: int) -> None:
    """Revokes the App's access entirely (app-JWT authenticated, not an installation token)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        resp = await http.delete(
            f"{_GITHUB_API}/app/installations/{installation_id}",
            headers={
                "Authorization": f"Bearer {_app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
            },
        )
        if resp.status_code != 404:
            _raise_for_status(resp)
