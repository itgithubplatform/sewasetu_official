# Sewa Setu — Old Age Pension Portal

Department of Social Welfare, Government of Purvanchal. Maintained in-house.

## Running

```
If you do not already have a local `.env`, copy `.env.example` to `.env` and set
`ADMIN_PASSWORD`. Then run:

```
docker compose up --build
```
```

- Portal: http://localhost:8000
- Status portal: http://localhost:8000/status (mobile number + password; the
  password is the applicant's date of birth as DDMMYYYY)
- Departmental login: http://localhost:8000/admin (user `admin`, password from
  `ADMIN_PASSWORD`)
- SMS gateway console (simulated telecom): http://localhost:8000/__gateway/ —
  OTPs and notifications appear here once "delivered" (1–4 s carrier latency).
  The gateway's inbox is also readable as JSON at
  `/__gateway/api/messages?to=<mobile>`.
- Database: Postgres, loaded from `seed/seed.sql` on first boot (~100k applications).
- Citizen MCP (streamable HTTP): http://localhost:8001/mcp
- Block officer MCP (streamable HTTP): http://localhost:8002/mcp
- Persona and evaluation dashboard: http://localhost:8000/eval-dashboard

The default MCP block allowlist is **Sonari only**. Set `MCP_ENABLED_BLOCKS` to a
comma-separated subset of the portal's blocks when deploying. The same server-side
allowlist gates agent application submissions, the officer queue, case lookup and
decisions. The normal web portal retains its existing block coverage.

## Deploying on a server

Set `PUBLIC_BASE_URL` to the address people will use (for example
`https://sewasetu.example.in`). It is stamped into sign-in tokens and the discovery documents
described below, so a wrong value means other applications cannot find the sign-in page. Put
the portal behind HTTPS; some applications refuse to sign in over plain HTTP.

```
PUBLIC_BASE_URL=https://sewasetu.example.in ADMIN_PASSWORD=pick-something docker compose up --build -d
```

## What the portal does

Citizen flow: mobile → OTP → personal details → address → bank details →
age-proof upload → preview and declaration → application number. A nightly
job (`scripts/deemed_approval.py`, via cron in the `scheduler` container)
deems approved any application still pending after the 15-day statutory SLA.

Rules enforced at submission, in `validate_application()` in `app/app.py`:
applicant is 60 years of age or above; required fields and an age-proof
document are present; the scheme window is open; and the mobile number holds
no other active (pending / approved / deemed-approved) application. A pending
application can be withdrawn from the status portal, after which the same
mobile may apply again.

Departmental users see a dashboard, list and filter applications, approve or
reject pending ones, and see the audit trail per application.

## Layout

```
app/          Flask application, templates, config, nightly job
dashboard/    evaluation dashboard served by the portal
evals/        synthetic personas, real-MCP-client evaluation runner and results
mcp_servers/  separate citizen and officer streamable-HTTP MCP servers
seed/         seed.sql — production data snapshot
smsgw/        simulated SMS gateway
```

## AI assistant connections

The MCP servers use Sewa Setu OAuth 2.1 bearer tokens; they do not accept OTPs,
passwords, or caller-supplied mobile identities. A citizen signs in and consents
to the citizen resource, and an officer signs in and consents to the officer
resource. Each server verifies the portal signature, issuer, audience, role and
scope. Keep the citizen and officer URLs separate in the assistant configuration.

Citizen tools:

- `pension_scheme_information` - read the current portal rules and enabled blocks.
- `submit_pension_application` - submit for the token's verified mobile; the
  portal applies its normal age, required-field, block, scheme-window, document,
  IFSC and duplicate-active-application checks. The user must explicitly confirm
  the declaration, and an age-proof file (PDF/JPG/PNG, at most 5 MB) is required.
- `check_my_application` - check the latest application tied to that mobile.

Officer tools:

- `list_pending_applications` - see the pending queue for enabled blocks.
- `review_application` - read the case fields and audit trail.
- `decide_on_application` - approve or reject a pending case with a required
  reason. The portal records the authenticated officer and decision in the
  existing application row and audit log.

An officer's program token can be issued at `/admin/tokens` with the officer MCP
resource URL as its audience. For user-consented sessions use the OAuth flow in
the assistant client; citizens and officers must never share their access tokens.
On deployment, set `PUBLIC_BASE_URL`, `CITIZEN_RESOURCE_URL` and
`OFFICER_RESOURCE_URL` to the exact HTTPS addresses used by people and MCP clients.
The audience URL must exactly match the resource used when issuing each token.

## Persona evaluation

The dashboard at `/eval-dashboard` shows the synthetic citizens, their scenarios,
MCP conversations, database checks and results. The runner uses actual
streamable-HTTP MCP client sessions and checks Postgres records and audit rows;
it does not call a model or infer success from the assistant's wording. The
runner creates and approves a synthetic application, so run it only in an
isolated evaluation deployment with synthetic identities and a database shared
by that deployment's portal and MCP services.

Install `requirements-mcp.txt`, start the services, then provide:

- `EVAL_DATABASE_URL`: connection string for the disposable portal database.
- `EVAL_CITIZEN_TOKENS`: JSON object mapping each persona ID in
  `evals/personas.json` to a fresh citizen token with the citizen MCP audience.
- `EVAL_OFFICER_TOKEN`: a fresh officer token for the officer MCP audience.
- `CITIZEN_MCP_URL` and `OFFICER_MCP_URL` only when using non-default endpoints.

Citizen tokens require a citizen sign-in and consent and expire quickly. Do not
put live tokens in source control or evaluation results. Without credentials the
runner records `not_run`; it never claims an evaluation passed if it was not
executed. Run `python -m evals.run_evals` from a machine that can reach the
portal database and both MCP endpoints, or use the optional Compose eval runner:
`docker compose --profile eval run --rm eval-runner`. Set `EVAL_DATABASE_URL`
in the local `.env` to the isolated deployment's database URL; the runner
reaches that database and MCP services on the private container network.

## Letting other applications act for a citizen or an officer

Sewa Setu is also an **OAuth 2.1 authorization server**. A third-party application can act
for a citizen (scope `citizen`) or for a block officer (scope `officer`) once that person
signs in on the portal and approves it. Citizens sign in by mobile and OTP, officers with the
departmental login. The application never handles the OTP or the password.

- Discovery: `/.well-known/oauth-authorization-server` (RFC 8414)
- Registration: `/oauth/register` (RFC 7591), or a client ID metadata document URL as `client_id`
- Authorization: `/oauth/authorize` (authorization code with PKCE S256; the `resource` the
  application asks for becomes the token's audience, RFC 8707)
- Tokens: `/oauth/token`. Access tokens are RS256 JWTs. A sign-in is a **session with an
  absolute end**: 2 hours for a citizen, 8 hours for an officer, counted from the consent.
  Access tokens are short (20 / 30 minutes) and refresh tokens rotate within the session but
  never extend it; after it ends the person signs in again. Portals are used on shared phones
  and kiosks.
- Sign-out: `/oauth/revoke` (RFC 7009). People can also end any sign-in from the status
  portal (**Connected applications**) or, for officers, the admin dashboard.
- Keys: `/.well-known/jwks.json`

A service that receives one of these tokens verifies it with the JWKS, checks `iss` is this
portal, checks `aud` is its own canonical URL, and reads `scope`, `role` and `sub`
(`citizen:<mobile>` or `officer:<username>`).

Long-lived **program tokens** for unattended use (role officer) are issued by an
administrator at `/admin/tokens`.
