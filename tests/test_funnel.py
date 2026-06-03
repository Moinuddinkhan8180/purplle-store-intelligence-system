# PROMPT:
# Generate funnel endpoint tests

# CHANGES MADE:
# Added response validation

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_funnel():

    response = client.get(
        "/stores/STORE_BLR_001/funnel"
    )

    assert response.status_code == 200