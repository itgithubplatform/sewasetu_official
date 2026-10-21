from mcp.server.auth.middleware.auth_context import get_access_token

from mcp_servers.common.errors import AuthorizationError
from mcp_servers.common.portal_client import PortalClient


def _access_token() -> str:
    access = get_access_token()
    if access is None:
        raise AuthorizationError("Sign in as a block officer before using this tool.")
    return access.token


def list_pending_applications(limit: int = 20) -> dict:
    """List pending applications for the agent-enabled blocks."""
    return PortalClient().request(
        "GET",
        "/api/agent/officer/applications",
        _access_token(),
        params={"limit": limit},
    )


def get_application(application_id: int) -> dict:
    """Read a case and audit trail within the agent-enabled block queue."""
    return PortalClient().request(
        "GET",
        f"/api/agent/officer/applications/{application_id}",
        _access_token(),
    )


def decide_application(application_id: int, decision: str, reason: str) -> dict:
    """Record an explicit officer decision with an audit reason."""
    return PortalClient().request(
        "POST",
        f"/api/agent/officer/applications/{application_id}/decision",
        _access_token(),
        json_body={"decision": decision, "reason": reason},
    )
