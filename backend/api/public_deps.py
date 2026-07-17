"""Anonymous visitor identity for public share-link routes.

No accounts, no login: each browser is handed an unguessable random UUID in
an httpOnly cookie on first contact with any public share-link endpoint.
Every chat session that visitor creates is tagged with this id, so listing
or reading sessions can be scoped strictly to "this cookie" — enough to keep
unrelated visitors from ever seeing each other's conversations.
"""

import uuid

from fastapi import Request, Response

from config import settings

_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 400  # ~400 days, the browser-enforced cap


def get_visitor_id(request: Request, response: Response) -> uuid.UUID:
    raw = request.cookies.get(settings.share_visitor_cookie_name)
    if raw is not None:
        try:
            return uuid.UUID(raw)
        except ValueError:
            pass  # malformed/tampered cookie — issue a fresh identity below

    visitor_id = uuid.uuid4()
    response.set_cookie(
        key=settings.share_visitor_cookie_name,
        value=str(visitor_id),
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
    )
    return visitor_id
