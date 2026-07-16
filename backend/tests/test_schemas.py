import uuid

import pytest
from pydantic import ValidationError

from models.schemas import (
    AgentCreate,
    AgentUpdate,
    ChatRequest,
    ProjectCreate,
)

# ── ProjectCreate ─────────────────────────────────────────────────────────────


def test_project_create_requires_name():
    with pytest.raises(ValidationError):
        ProjectCreate()  # type: ignore[call-arg]


def test_project_create_description_defaults_to_none():
    p = ProjectCreate(name="Contracts")
    assert p.name == "Contracts"
    assert p.description is None


def test_project_create_accepts_description():
    p = ProjectCreate(name="Legal", description="Legal documents")
    assert p.description == "Legal documents"


# ── AgentCreate ───────────────────────────────────────────────────────────────


def test_agent_create_requires_name():
    with pytest.raises(ValidationError):
        AgentCreate()  # type: ignore[call-arg]


def test_agent_create_defaults():
    a = AgentCreate(name="Assistant")
    assert a.top_k == 2
    assert a.system_prompt == ""
    assert a.description is None


def test_agent_create_accepts_all_fields():
    a = AgentCreate(
        name="Bot", description="Helpful", system_prompt="Be concise.", top_k=5
    )
    assert a.top_k == 5
    assert a.system_prompt == "Be concise."


# ── AgentUpdate ───────────────────────────────────────────────────────────────


def test_agent_update_all_fields_optional():
    u = AgentUpdate()
    assert u.name is None
    assert u.description is None
    assert u.system_prompt is None
    assert u.top_k is None


def test_agent_update_partial():
    u = AgentUpdate(name="New name", top_k=10)
    assert u.name == "New name"
    assert u.top_k == 10
    assert u.system_prompt is None


# ── ChatRequest ───────────────────────────────────────────────────────────────


def test_chat_request_requires_question():
    with pytest.raises(ValidationError):
        ChatRequest(session_id=uuid.uuid4())  # type: ignore[call-arg]


def test_chat_request_requires_session_id():
    with pytest.raises(ValidationError):
        ChatRequest(question="What is the invoice total?")  # type: ignore[call-arg]


def test_chat_request_stores_question():
    sid = uuid.uuid4()
    r = ChatRequest(question="What is the invoice total?", session_id=sid)
    assert r.question == "What is the invoice total?"
    assert r.session_id == sid
