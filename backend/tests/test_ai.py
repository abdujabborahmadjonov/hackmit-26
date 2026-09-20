"""Generative endpoints.

No API key runs in CI, so these cover the contract around the model: the
disabled path, authorisation, validation, and that the prompt is built from
real profile facts. The one test that would call Claude is skipped unless a
key is present.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from app.config import settings
from app.services import llm_service
from tests.conftest import register, register_with_profile, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_status_reports_disabled_without_a_key(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    response = await client.get("/ai/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "features": []}


async def test_status_lists_features_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-ant-test")
    body = (await client.get("/ai/status")).json()
    assert body["enabled"] is True
    assert set(body["features"]) == {"collaboration_brief", "profile_import"}


async def test_brief_is_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    alice = await register_with_profile(client, first_name="Alice")
    bob = await register_with_profile(client, first_name="Bob")
    response = await client.get(f"/ai/brief/{bob['user_id']}", headers=alice["headers"])
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


async def test_brief_requires_authentication(client):
    bob = await register_with_profile(client, first_name="Bob")
    assert (await client.get(f"/ai/brief/{bob['user_id']}")).status_code == 401


async def test_brief_requires_your_own_profile(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-ant-test")
    bob = await register_with_profile(client, first_name="Bob")
    profileless = await register(client, first_name="New")
    response = await client.get(f"/ai/brief/{bob['user_id']}", headers=profileless["headers"])
    assert response.status_code == 400
    assert "profile" in response.json()["detail"].lower()


async def test_brief_refuses_yourself(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-ant-test")
    alice = await register_with_profile(client, first_name="Alice")
    response = await client.get(f"/ai/brief/{alice['user_id']}", headers=alice["headers"])
    assert response.status_code == 400


async def test_document_import_validates_its_input(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-ant-test")
    account = await register(client)

    empty = await client.post("/ai/profile-from-document", headers=account["headers"], data={})
    assert empty.status_code == 400

    wrong_type = await client.post(
        "/ai/profile-from-document",
        headers=account["headers"],
        files={"file": ("notes.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert wrong_type.status_code == 415


async def test_document_import_is_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    account = await register(client)
    response = await client.post(
        "/ai/profile-from-document",
        headers=account["headers"],
        data={"text": "A syllabus long enough to be worth reading by the model."},
    )
    assert response.status_code == 503


# --- prompt construction: the part that must stay grounded ----------------- #
def test_profile_facts_carry_the_real_attributes():
    from app.models.profile import TeacherProfile
    from app.services.llm_service import _profile_facts

    profile = TeacherProfile(
        subjects=["computer_science", "python"],
        education_levels=["high_school"],
        teaching_levels=["beginner"],
        teaching_methods=["project_based"],
        fields_of_expertise=["software_engineering"],
        teaching_style="Students ship a working app each unit.",
        class_size=25,
        years_experience=5,
        institution="Boston Latin School",
        location_name="Boston, Massachusetts",
    )
    facts = _profile_facts("Teacher A", profile, "Alice")
    for fragment in (
        "Alice",
        "Computer Science",
        "High School",
        "Project Based",
        "Boston Latin School",
        "Students ship a working app each unit.",
        "25",
    ):
        assert fragment in facts


def test_extraction_schema_pins_the_vocabularies():
    """The model is told the allowed slugs, not left to invent them."""
    from app.services.llm_service import ExtractedProfile

    schema = ExtractedProfile.model_json_schema()
    assert "high_school" in schema["properties"]["education_levels"]["description"]
    assert "project_based" in schema["properties"]["teaching_methods"]["description"]
    assert "snake_case" in schema["properties"]["subjects"]["description"]


def test_disabled_service_raises_rather_than_calling_out(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(llm_service.LLMUnavailable, match="LLM_API_KEY"):
        llm_service._client()


@pytest.mark.skipif(not settings.llm_api_key, reason="needs a real LLM_API_KEY")
async def test_brief_against_the_real_model(client):
    """The only test that spends money. Runs when a key is configured."""
    alice = await register_with_profile(client, first_name="Alice")
    bob = await register_with_profile(
        client,
        first_name="Bob",
        subjects=["computer_science", "python"],
        teaching_methods=["project_based"],
        teaching_style="Students build working apps in pairs with peer review.",
    )
    response = await client.get(f"/ai/brief/{bob['user_id']}", headers=alice["headers"])
    assert response.status_code == 200, response.text
    brief = response.json()["brief"]
    assert 60 < len(brief.split()) < 220
    assert "Bob" in brief


def test_generation_uses_the_namespace_that_accepts_fallbacks():
    """`betas`/`fallbacks` exist only on client.beta.messages.* - calling the
    plain namespace with them raises TypeError at request time, which is a 503
    to the user and invisible until something actually calls the model."""
    import inspect

    from anthropic.resources.beta.messages.messages import AsyncMessages as BetaMessages
    from anthropic.resources.messages.messages import AsyncMessages as StdMessages

    beta_params = set(inspect.signature(BetaMessages.create).parameters)
    std_params = set(inspect.signature(StdMessages.create).parameters)
    assert {"betas", "fallbacks"} <= beta_params
    assert not {"betas", "fallbacks"} & std_params

    source = pathlib.Path("app/services/llm_service.py").read_text()
    assert "client.beta.messages.create(" in source
    assert "client.beta.messages.parse(" in source
    assert "await client.messages.create(" not in source
    assert "await client.messages.parse(" not in source
