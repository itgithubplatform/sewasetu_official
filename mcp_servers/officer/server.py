from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from mcp_servers.common.auth import PortalTokenVerifier
from mcp_servers.common.config import (
    OFFICER_MCP_PORT,
    OFFICER_RESOURCE_URL,
    PORTAL_ISSUER_URL,
)
from mcp_servers.officer.tools import (
    decide_application as record_decision,
    get_application as read_application,
    list_pending_applications as read_pending_applications,
)

mcp = FastMCP(
    "Sewa Setu Block Officer",
    instructions=(
        "Support the authenticated block officer by reviewing the configured "
        "agent-enabled block queue and recording an approve/reject decision with "
        "a reason. Never decide a case without the officer's explicit instruction."
    ),
    host="0.0.0.0",
    port=OFFICER_MCP_PORT,
    streamable_http_path="/mcp",
    auth=AuthSettings(
        issuer_url=PORTAL_ISSUER_URL,
        resource_server_url=OFFICER_RESOURCE_URL,
        validate_token_resource=False,
        required_scopes=["officer"],
    ),
    token_verifier=PortalTokenVerifier(OFFICER_RESOURCE_URL, "officer"),
)


@mcp.tool()
def list_pending_applications(limit: int = 20) -> dict:
    """List pending applications in the agent-enabled block queue."""
    return read_pending_applications(limit=limit)


@mcp.tool()
def review_application(application_id: int) -> dict:
    """Read an application and its audit trail before making a decision."""
    return read_application(application_id=application_id)


@mcp.tool()
def decide_on_application(
    application_id: int,
    decision: str,
    reason: str,
) -> dict:
    """Approve or reject a pending application with a recorded reason."""
    return record_decision(
        application_id=application_id,
        decision=decision,
        reason=reason,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
