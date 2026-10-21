import pytest

from mcp_servers.common.errors import PortalIntegrationError
from mcp_servers.common.portal_client import PortalClient


def test_rejects_invalid_api_path():
    client = PortalClient("http://localhost:8000")

    with pytest.raises(ValueError):
        client.request(
            "GET",
            "//untrusted.example/path",
            "not-a-real-token",
        )


def test_sends_portal_bearer_token(monkeypatch):
    import requests

    captured = {}

    class Response:
        is_redirect = False
        status_code = 200

        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    def fake_request(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    result = PortalClient("http://portal").request(
        "GET",
        "/api/agent/citizen/application",
        "test-access-token",
    )

    assert result == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer test-access-token"


def test_returns_portal_validation_message(monkeypatch):
    import requests

    class Response:
        is_redirect = False
        status_code = 400

        def json(self):
            return {
                "error": "Application validation failed.",
                "validation_errors": ["applicant must be 60 years of age or above"],
            }

    monkeypatch.setattr(requests, "request", lambda **kwargs: Response())

    with pytest.raises(PortalIntegrationError, match="60 years"):
        PortalClient("http://portal").request(
            "POST",
            "/api/agent/citizen/applications",
            "test-access-token",
            json_body={},
        )