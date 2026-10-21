# Sewa Setu agent integration - implementation and handoff

## What is implemented

- Two separate streamable-HTTP MCP servers are available at
  `http://localhost:8001/mcp` (citizen) and `http://localhost:8002/mcp` (officer).
  The citizen server exposes scheme information, application submission and the
  applicant's own status. The officer server exposes the enabled-block queue,
  case review and approve/reject decisions. Their tool lists do not overlap.
- Both servers accept only portal-issued bearer tokens. Each verifies the
  signature, issuer, exact audience, role and scope. A citizen token cannot use
  officer tools, and neither MCP tool accepts a caller-selected mobile or actor.
  Resource metadata advertises the same canonical issuer as portal OAuth
  discovery; verification remains compatible with tokens issued before the
  issuer-format change.
- The portal exposes the tools' API routes in [app/agent_api.py](./app/agent_api.py).
  Submissions use the portal's existing `validate_application()` and
  `create_application()` logic, save age proof under the portal upload directory,
  and create the normal application and audit rows. A transaction advisory lock
  in [app/app.py](./app/app.py) serializes active-application checks across both
  web and MCP submission paths. The MCP block allowlist defaults to **Sonari**;
  it also gates the officer queue, case access and decisions.
- Officer decisions require a reason and write the authenticated officer and
  reason to the portal's application row and audit log. The portal remains the
  system of record, so web and MCP channels use the same database.
- [dashboard/eval_dashboard.py](./dashboard/eval_dashboard.py) serves
  `/eval-dashboard`; [evals/personas.json](./evals/personas.json) defines three
  specific synthetic citizens. [evals/run_evals.py](./evals/run_evals.py) uses
  actual MCP streamable-HTTP client sessions and verifies application, file,
  duplicate, status, queue, decision and audit state directly in Postgres.

## Design note

1. **Separate citizen and officer MCP endpoints.** This keeps officer tools out
   of a citizen assistant's tool list and makes audience/role validation
   explicit.
2. **Reuse the portal's validator and record-creation path.** MCP submissions
   cannot bypass age, required fields, block scope, scheme window, proof,
   IFSC or active-application checks. The portal's shared active check now also
   locks by verified mobile so concurrent web/MCP requests cannot both pass.
3. **Keep decisions attributable and bounded.** Officer decisions require a
   reason, persist the token subject as the officer, and are limited to the
   configured blocks. The default is one block, Sonari.

With more time, I would replace the simple JSON/base64 age-proof transfer with
an assistant-client upload flow that can show the document as a native
attachment before submission and support a human-confirmed declaration step
without relying on the assistant to relay a boolean. The current tool requires
an age-proof file and an explicit declaration flag; assistant UX must still
ask the applicant to review the complete details and confirm before calling
submit.

## Personas and evals

| Citizen | Scenario | Required portal result |
|---|---|---|
| Kamla Devi, 70, Sonari Basti | Speaks simply and asks her grandson to help; seeks the pension. | One pending Sonari application for her verified mobile, age proof and submit audit; duplicate attempt denied; status follows the same row. |
| Shanti Devi, 59, Sonari Basti | Asks to apply before her 60th birthday. | Portal age rule rejects her; no application is created. |
| Rahim Ansari, 68, Rajapara Bazaar | Gives details politely and asks whether his nearby block is covered. | Agent-only block boundary rejects him; no application is created. |

The officer part of Kamla's scenario checks queue visibility, case/audit review,
an approval with a synthetic reason, officer attribution in the database, and
the citizen's updated status. The evaluator uses new synthetic identities and
must run only against an isolated deployment whose portal and evaluator share
the same disposable database. Set `EVAL_DATABASE_URL`,
`EVAL_CITIZEN_TOKENS` (persona ID to fresh token), and `EVAL_OFFICER_TOKEN`,
then run `docker compose --profile eval run --rm eval-runner` or
`python -m evals.run_evals` from a host that can reach those services.

**Eval result: not run.** No live citizen/officer consent tokens or separate
evaluation database were supplied. The dashboard and
[evals/results/results.json](./evals/results/results.json) say `not_run`;
there is no asserted pass rate or claimed conversation outcome yet.

## Verification completed

- Focused and full available pytest suite: **18 passed**.
- Python modules compiled successfully.
- `docker compose config` and `docker compose --profile eval config` passed.
- `docker compose build` passed for portal, scheduler, SMS gateway and both MCP
  images.
- The local Compose deployment is running. Portal home, about, official scheme
  API, OAuth metadata, JWKS and eval dashboard returned HTTP 200. The scheme API
  reports Sonari. Both MCP endpoints returned HTTP 401 with an OAuth resource
  metadata challenge when called without credentials. No application was
  submitted during the smoke checks.

## Local walkthrough

1. If no local `.env` exists, copy `.env.example` to `.env`; set a strong
   `ADMIN_PASSWORD`, and run `docker compose up --build -d`. This local stack is
   already running.
2. Open the portal at `http://localhost:8000/` and the evaluation page at
   `http://localhost:8000/eval-dashboard`. Interactive form URLs in
   [PORTAL_URLS.txt](./PORTAL_URLS.txt) require the expected browser session.
3. Connect a citizen assistant to `http://localhost:8001/mcp` and an officer
   assistant separately to `http://localhost:8002/mcp`. Complete the portal's
   OAuth sign-in and consent for the matching MCP resource; do not reuse tokens.
4. To run the written evals, use a cloned/isolated deployment and synthetic
   identities, set the three `EVAL_*` environment variables from
   [README.md](./README.md), then run the evaluator. Review database assertions
   both in the results file and at `/eval-dashboard`.
5. Record the requested Loom only after those real evals finish, and include
   their actual pass rate and lessons rather than presenting the current
   `not_run` state as a result.

## Remaining external handoff

- No public VM/deployment URL was provided; the current reachable endpoints are
  local defaults. Set the exact public HTTPS values for `PUBLIC_BASE_URL`,
  `CITIZEN_RESOURCE_URL` and `OFFICER_RESOURCE_URL` before deployment.
- A Loom recording was not created or uploaded. Record a face-and-screen video
  of no more than three minutes after running the real evals; cover the two MCP
  designs, personas, eval outcomes and changes learned from those outcomes.
- No private GitHub repository, collaborator invitation or `.git` zip was
  created. Those brief submission steps require the target account/repository
  and external access.

For the complete local and deployment URL checklist, see [PORTAL_URLS.txt](./PORTAL_URLS.txt).
Operational setup, tool descriptions and eval instructions are in [README.md](./README.md).
