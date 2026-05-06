"""
Basic health check test.
Uses the shared client fixture from conftest (avoids TestClient init at import time).
"""


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

