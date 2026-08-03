import pytest


@pytest.mark.asyncio
async def test_register(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "firstName": "Ayesha",
            "lastName": "Khan",
            "email": "ayesha@example.com",
            "password": "password123",
            "phone": "+92 300 1234567",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "firstName": "User",
            "lastName": "One",
            "email": "duplicate@example.com",
            "password": "password123",
        },
    )

    # Try registering again with same email
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "firstName": "User",
            "lastName": "Two",
            "email": "duplicate@example.com",
            "password": "password456",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login(client, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["firstName"] == "Test"
    assert data["lastName"] == "User"
    assert "addresses" in data


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client, test_user):
    # Login first
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    tokens = login_response.json()

    # Refresh
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": tokens["refreshToken"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data


# ── Logout ──────────────────────────────────────────────────────


async def _login(client, email="test@example.com", password="password123"):
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return response.json()


@pytest.mark.asyncio
async def test_logout_returns_ok(client, test_user):
    tokens = await _login(client)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"


@pytest.mark.asyncio
async def test_access_token_rejected_after_logout(client, test_user):
    tokens = await _login(client)
    headers = {"Authorization": f"Bearer {tokens['accessToken']}"}

    # Works before logout
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    await client.post("/api/v1/auth/logout", headers=headers)

    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["detail"] == "Token has been revoked"


@pytest.mark.asyncio
async def test_logout_does_not_affect_other_sessions(client, test_user):
    """Per-device logout: a second login's token must keep working."""
    first = await _login(client)
    second = await _login(client)

    await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {first['accessToken']}"},
    )

    still_valid = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {second['accessToken']}"},
    )
    assert still_valid.status_code == 200


@pytest.mark.asyncio
async def test_revoked_refresh_token_cannot_mint_new_tokens(client, test_user):
    tokens = await _login(client)

    await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
        json={"refreshToken": tokens["refreshToken"]},
    )

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]}
    )
    assert refreshed.status_code == 401
    assert refreshed.json()["detail"] == "Refresh token has been revoked"


@pytest.mark.asyncio
async def test_refresh_still_works_without_logout(client, test_user):
    """Guards against the denylist check rejecting healthy refresh tokens."""
    tokens = await _login(client)
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]}
    )
    assert refreshed.status_code == 200


@pytest.mark.asyncio
async def test_logout_is_idempotent(client, test_user):
    tokens = await _login(client)
    headers = {"Authorization": f"Bearer {tokens['accessToken']}"}

    first = await client.post("/api/v1/auth/logout", headers=headers)
    assert first.status_code == 200

    # Second attempt uses a now-revoked token, so the guard rejects it
    second = await client.post("/api/v1/auth/logout", headers=headers)
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_logout_requires_authentication(client):
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_ignores_another_users_refresh_token(client, test_user, admin_user):
    """One account must not be able to revoke another's session."""
    victim = await _login(client, "admin@example.com", "admin123")
    attacker = await _login(client)

    await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {attacker['accessToken']}"},
        json={"refreshToken": victim["refreshToken"]},
    )

    # Victim's refresh token must still be usable
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": victim["refreshToken"]}
    )
    assert refreshed.status_code == 200
