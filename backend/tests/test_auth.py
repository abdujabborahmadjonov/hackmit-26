"""Registration, login and token handling."""

from __future__ import annotations

import pytest

from tests.conftest import DEFAULT_PASSWORD, register, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_register_returns_a_token(client):
    response = await client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": DEFAULT_PASSWORD,
            "first_name": "Alice",
            "last_name": "Nguyen",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert "password" not in response.text.lower()


async def test_duplicate_email_is_rejected(client):
    await register(client, email="dup@example.com")
    response = await client.post(
        "/auth/register",
        json={
            "email": "DUP@example.com",  # case-insensitive
            "password": DEFAULT_PASSWORD,
            "first_name": "Other",
            "last_name": "Person",
        },
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "password,reason",
    [("short1", "too short"), ("nodigitshere", "no digit"), ("12345678", "no letter")],
)
async def test_weak_passwords_are_rejected(client, password, reason):
    response = await client.post(
        "/auth/register",
        json={
            "email": f"weak-{reason.replace(' ', '')}@example.com",
            "password": password,
            "first_name": "Weak",
            "last_name": "Password",
        },
    )
    assert response.status_code == 422, reason


async def test_login_succeeds_and_rejects_bad_credentials(client):
    account = await register(client, email="login@example.com")

    ok = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": account["password"]}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    wrong = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "WrongPassword123"}
    )
    assert wrong.status_code == 401

    unknown = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    )
    # Identical response shape: no account enumeration.
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


async def test_me_requires_a_valid_token(client):
    account = await register(client, first_name="Ada")

    me = await client.get("/auth/me", headers=account["headers"])
    assert me.status_code == 200
    body = me.json()
    assert body["first_name"] == "Ada"
    assert body["email"] == account["email"]
    assert "password_hash" not in body
    assert "password" not in body

    assert (await client.get("/auth/me")).status_code == 401
    assert (
        await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    ).status_code == 401


async def test_password_hash_is_never_plaintext(client, db_session):
    from sqlalchemy import select

    from app.models.user import User

    account = await register(client, email="hash@example.com")
    user = await db_session.scalar(select(User).where(User.email == "hash@example.com"))
    assert user is not None
    assert user.password_hash != account["password"]
    assert user.password_hash.startswith("$argon2")


async def test_change_password_flow(client):
    account = await register(client, email="change@example.com")
    response = await client.post(
        "/auth/change-password",
        json={"current_password": account["password"], "new_password": "BrandNewPass123"},
        headers=account["headers"],
    )
    assert response.status_code == 200

    old = await client.post(
        "/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login", json={"email": account["email"], "password": "BrandNewPass123"}
    )
    assert new.status_code == 200


async def test_wrong_current_password_is_rejected(client):
    account = await register(client)
    response = await client.post(
        "/auth/change-password",
        json={"current_password": "NotMyPassword1", "new_password": "BrandNewPass123"},
        headers=account["headers"],
    )
    assert response.status_code == 400
