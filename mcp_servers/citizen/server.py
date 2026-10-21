from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from mcp_servers.citizen.tools import (
    get_application_status as check_application_status,
    get_scheme_information,
    submit_pension_application as create_pension_application,
)
from mcp_servers.common.auth import PortalTokenVerifier
from mcp_servers.common.config import (
    CITIZEN_MCP_PORT,
    CITIZEN_RESOURCE_URL,
    PORTAL_ISSUER_URL,
)

mcp = FastMCP(
    "Sewa Setu Citizen",
    instructions=(
        "Help a citizen apply for or check their own Old Age Pension application. "
        "Use official portal rules and do not promise eligibility. Submission requires "
        "the applicant's age-proof document and explicit declaration."
    ),
    host="0.0.0.0",
    port=CITIZEN_MCP_PORT,
    streamable_http_path="/mcp",
    auth=AuthSettings(
        issuer_url=PORTAL_ISSUER_URL,
        resource_server_url=CITIZEN_RESOURCE_URL,
        validate_token_resource=False,
        required_scopes=["citizen"],
    ),
    token_verifier=PortalTokenVerifier(CITIZEN_RESOURCE_URL, "citizen"),
    max_request_body_size=8 * 1024 * 1024,
)


@mcp.tool()
def pension_scheme_information() -> dict:
    """Get current pension rules and blocks enabled for agent applications."""
    return get_scheme_information()


@mcp.tool()
def check_my_application() -> dict:
    """Check the authenticated citizen's latest pension application status."""
    return check_application_status()


@mcp.tool()
def submit_pension_application(
    applicant_name: str,
    date_of_birth: str,
    village: str,
    block: str,
    bank_account: str,
    age_proof_filename: str,
    age_proof_base64: str,
    declaration_confirmed: bool,
    ifsc: str = "",
    gender: str = "",
    marital_status: str = "",
    husband_name: str = "",
) -> dict:
    """Submit an application for the authenticated citizen through portal validation.

    Date of birth must be DD/MM/YYYY. Supply the age-proof file as base64 and set
    declaration_confirmed only after the citizen has reviewed the declaration.
    """
    return create_pension_application(
        applicant_name=applicant_name,
        date_of_birth=date_of_birth,
        village=village,
        block=block,
        bank_account=bank_account,
        age_proof_filename=age_proof_filename,
        age_proof_base64=age_proof_base64,
        declaration_confirmed=declaration_confirmed,
        ifsc=ifsc,
        gender=gender,
        marital_status=marital_status,
        husband_name=husband_name,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
