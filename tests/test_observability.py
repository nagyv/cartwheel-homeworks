import pytest
from fastapi.testclient import TestClient

from server import app as server_app


@pytest.fixture
def client(world):
    server_app._SESSIONS.clear()
    yield TestClient(server_app.app)
    server_app._SESSIONS.clear()


def test_create_session_rejects_a_role_that_differs_from_the_database(client):
    response = client.post("/sessions", json={"user_id": 1, "role": "support"})

    assert response.status_code == 403
    assert server_app._SESSIONS == {}


def test_a_token_for_one_session_cannot_authorize_another_session(client):
    first = client.post("/sessions", json={"user_id": 1, "role": "shopper"}).json()
    second = client.post("/sessions", json={"user_id": 9002, "role": "merchant"}).json()

    response = client.post(
        f"/sessions/{second['session_id']}/messages",
        headers={"Authorization": f"Bearer {first['token']}"},
        json={"message": "Show me order 4127."},
    )

    assert response.status_code == 403
