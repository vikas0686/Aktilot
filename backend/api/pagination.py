"""Shared FastAPI query-param types for paginating list endpoints.

Every list endpoint previously returned its full table scan with no limit,
so a project/agent that accumulates enough rows (chat messages especially,
which grow without bound for the lifetime of an agent) would eventually
return an unbounded response on every single call. These types cap the page
size and let callers page through the rest with `offset`.
"""

from typing import Annotated

from fastapi import Query

# Default pagination for small/slow-growing collections (projects, files,
# agents, sessions, github connections).
LimitParam = Annotated[
    int, Query(ge=1, le=500, description="Max number of items to return")
]

# Messages grow unboundedly for the lifetime of an agent/session, so they get
# a larger default/ceiling than other list endpoints.
MessageLimitParam = Annotated[
    int, Query(ge=1, le=1000, description="Max number of items to return")
]

OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]
