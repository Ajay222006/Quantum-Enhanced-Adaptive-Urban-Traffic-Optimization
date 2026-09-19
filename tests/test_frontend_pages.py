from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
FRONTEND = Path(__file__).parents[1] / "frontend"


def test_all_frontend_pages_are_served():
    pages = sorted(FRONTEND.glob("*.html"))
    assert pages
    for page in pages:
        path = "/" if page.name == "index.html" else f"/{page.name}"
        response = client.get(path)
        assert response.status_code == 200, page.name
        assert "<!doctype html>" in response.text.lower(), page.name


def test_shared_frontend_assets_are_served():
    for asset in ("assets/app.js", "assets/styles.css", "assets/pages.css"):
        response = client.get(f"/{asset}")
        assert response.status_code == 200, asset
