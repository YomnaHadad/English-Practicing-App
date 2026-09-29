def test_register_login_me(client, auth):
    r = client.get("/api/users/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert "password" not in r.text


def test_duplicate_username_rejected(client, auth):
    r = client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "other@example.com", "password": "password123"},
    )
    assert r.status_code == 409


def test_wrong_password_rejected(client, auth):
    r = client.post("/api/auth/token", data={"username": "alice", "password": "nope-nope"})
    assert r.status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/api/users/me").status_code == 401
    assert client.get("/api/progress").status_code == 401
    assert client.get("/api/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
