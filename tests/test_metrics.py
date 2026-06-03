# PROMPT:
# Generate metrics endpoint tests

# CHANGES MADE:
# Added store validation

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics():

    response = client.get(
        "/stores/STORE_BLR_001/metrics"
    )

    assert response.status_code == 200