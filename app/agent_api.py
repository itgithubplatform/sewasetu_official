import base64
import binascii
import os
import re
import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request

import app as portal
from oauth import verify_token

agent_api = Blueprint("agent_api", __name__)
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def enabled_blocks():
    configured = os.getenv("MCP_ENABLED_BLOCKS", "Sonari")
    blocks = [block.strip() for block in configured.split(",") if block.strip()]
    invalid = [block for block in blocks if block not in portal.BLOCKS]
    if invalid or not blocks:
        raise RuntimeError("MCP_ENABLED_BLOCKS must contain valid portal blocks.")
    return list(dict.fromkeys(blocks))


def _authorized(role):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None, (jsonify(error="A Sewa Setu access token is required."), 401)

    resource = os.getenv(
        "CITIZEN_RESOURCE_URL" if role == "citizen" else "OFFICER_RESOURCE_URL",
        "http://localhost:8001/mcp" if role == "citizen"
        else "http://localhost:8002/mcp",
    ).rstrip("/")
    claims = verify_token(token, resource)
    if not claims:
        return None, (jsonify(error="The access token is invalid or expired."), 401)

    scopes = claims.get("scope", "")
    scopes = scopes.split() if isinstance(scopes, str) else scopes
    if claims.get("role") != role or role not in scopes:
        return None, (jsonify(error="This access token cannot perform this action."), 403)

    subject = claims.get("sub", "")
    prefix = "citizen:" if role == "citizen" else "officer:"
    identity = subject.removeprefix(prefix) if subject.startswith(prefix) else ""
    if not identity:
        return None, (jsonify(error="The access token has an invalid subject."), 403)
    if role == "citizen" and not re.fullmatch(r"\d{10}", identity):
        return None, (jsonify(error="The citizen identity is invalid."), 403)
    return (claims, identity), None


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify(error="A JSON object is required."), 400)
    return data, None


def _format_date(value):
    return value.isoformat() if value else None


@agent_api.get("/api/agent/scheme")
def scheme_information():
    try:
        blocks = enabled_blocks()
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500
    return jsonify({
        "scheme_name": "Old Age Pension",
        "monthly_amount_inr": 250,
        "minimum_age": portal.MIN_AGE,
        "residency": "Resident of Purvanchal",
        "enabled_blocks": blocks,
        "application_window_closes_at": _format_date(portal.SCHEME_DEADLINE),
        "requirements": [
            "Applicant is at least 60 years old",
            "Required personal and address details",
            "Bank account number; IFSC is validated when provided",
            "Age-proof document in PDF, JPG or PNG format, up to 5 MB",
            "Applicant's declaration",
            "No active application exists for the verified mobile number",
        ],
        "important_note": (
            "The portal validates and records every application. Scheme information "
            "is informational and is not a guarantee of eligibility or approval."
        ),
    })


@agent_api.get("/api/agent/citizen/application")
def citizen_application_status():
    auth, error = _authorized("citizen")
    if error:
        return error
    _, mobile = auth
    conn = portal.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, application_no, status, block, submitted_at, decided_at, "
            "decided_by FROM applications WHERE mobile = %s "
            "ORDER BY submitted_at DESC NULLS LAST LIMIT 1",
            (mobile,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(error="No application was found for this mobile number."), 404
        cur.execute(
            "SELECT note FROM audit_log WHERE application_id = %s "
            "AND action IN ('APPROVED', 'REJECTED', 'DEEMED_APPROVED') "
            "ORDER BY at DESC LIMIT 1",
            (row[0],),
        )
        reason_row = cur.fetchone()
        return jsonify({
            "application_id": row[0],
            "application_number": row[1],
            "status": row[2],
            "block": row[3],
            "submitted_at": _format_date(row[4]),
            "decided_at": _format_date(row[5]),
            "decided_by": row[6],
            "decision_note": reason_row[0] if reason_row else None,
        })
    finally:
        conn.close()


@agent_api.post("/api/agent/citizen/applications")
def submit_citizen_application():
    auth, error = _authorized("citizen")
    if error:
        return error
    _, mobile = auth
    data, error = _json_object()
    if error:
        return error
    if data.get("declaration_confirmed") is not True:
        return jsonify(error="The applicant must review and confirm the declaration."), 400

    try:
        blocks = enabled_blocks()
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500
    block = (data.get("block") or "").strip()
    if block not in blocks:
        return jsonify(
            error="Agent applications are not enabled for this block.",
            enabled_blocks=blocks,
        ), 400

    filename = data.get("age_proof_filename")
    encoded_document = data.get("age_proof_base64")
    if not isinstance(filename, str) or not isinstance(encoded_document, str):
        return jsonify(error="An age-proof filename and base64 document are required."), 400
    extension = os.path.splitext(filename)[1].lower()
    if extension not in DOCUMENT_EXTENSIONS:
        return jsonify(error="Age proof must be a PDF, JPG or PNG file."), 400
    if len(encoded_document) > ((MAX_DOCUMENT_BYTES + 2) // 3) * 4:
        return jsonify(error="Age-proof document must be 5 MB or smaller."), 413
    try:
        document = base64.b64decode(encoded_document, validate=True)
    except (binascii.Error, ValueError):
        return jsonify(error="Age-proof document is not valid base64."), 400
    if not document:
        return jsonify(error="Age-proof document cannot be empty."), 400
    if len(document) > MAX_DOCUMENT_BYTES:
        return jsonify(error="Age-proof document must be 5 MB or smaller."), 413

    errors, cleaned = portal.validate_application(data, "agent-age-proof")
    if errors:
        return jsonify(error="Application validation failed.", validation_errors=errors), 400

    conn = portal.get_db()
    document_path = None
    try:
        cur = conn.cursor()
        existing = portal.active_application(cur, mobile)
        if existing:
            conn.rollback()
            return jsonify(
                error="An active application already exists for this verified mobile number.",
                application_number=existing[1],
                status=existing[2],
            ), 409

        os.makedirs(portal.UPLOAD_DIR, exist_ok=True)
        document_path = os.path.join(
            portal.UPLOAD_DIR,
            "agent_%s%s" % (secrets.token_hex(16), extension),
        )
        with open(document_path, "wb") as document_file:
            document_file.write(document)
        cleaned["doc_path"] = document_path
        application_id, application_number = portal.create_application(
            cur,
            mobile,
            cleaned,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        if document_path and os.path.exists(document_path):
            os.remove(document_path)
        raise
    finally:
        conn.close()

    portal.send_sms(
        mobile,
        "Sewa Setu: application %s received. Track it at the official status portal."
        % application_number,
    )
    return jsonify({
        "application_id": application_id,
        "application_number": application_number,
        "status": "PENDING",
        "block": cleaned["block"],
        "submitted_at": datetime.now().isoformat(),
        "message": "The portal accepted and recorded the application.",
    }), 201


@agent_api.get("/api/agent/officer/applications")
def officer_pending_applications():
    auth, error = _authorized("officer")
    if error:
        return error
    try:
        blocks = enabled_blocks()
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500

    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        return jsonify(error="limit must be an integer between 1 and 50."), 400
    if not 1 <= limit <= 50:
        return jsonify(error="limit must be an integer between 1 and 50."), 400

    conn = portal.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, application_no, applicant_name, village, block, "
            "submitted_at FROM applications WHERE status = 'PENDING' "
            "AND block = ANY(%s) ORDER BY submitted_at ASC LIMIT %s",
            (blocks, limit),
        )
        rows = cur.fetchall()
        return jsonify({
            "enabled_blocks": blocks,
            "applications": [
                {
                    "application_id": row[0],
                    "application_number": row[1],
                    "applicant_name": row[2],
                    "village": row[3],
                    "block": row[4],
                    "submitted_at": _format_date(row[5]),
                }
                for row in rows
            ],
        })
    finally:
        conn.close()


@agent_api.get("/api/agent/officer/applications/<int:application_id>")
def officer_application(application_id):
    auth, error = _authorized("officer")
    if error:
        return error
    try:
        blocks = enabled_blocks()
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500

    conn = portal.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, application_no, applicant_name, mobile, dob, gender, "
            "marital_status, village, block, bank_account, ifsc, doc_path, status, "
            "submitted_at, decided_at, decided_by FROM applications "
            "WHERE id = %s AND block = ANY(%s)",
            (application_id, blocks),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(error="Application not found in the agent-enabled blocks."), 404
        cur.execute(
            "SELECT at, action, actor, note FROM audit_log "
            "WHERE application_id = %s ORDER BY at ASC",
            (application_id,),
        )
        audit = cur.fetchall()
        return jsonify({
            "application_id": row[0],
            "application_number": row[1],
            "applicant_name": row[2],
            "mobile": row[3],
            "date_of_birth": _format_date(row[4]),
            "gender": row[5],
            "marital_status": row[6],
            "village": row[7],
            "block": row[8],
            "bank_account": row[9],
            "ifsc": row[10],
            "age_proof_filename": os.path.basename(row[11]) if row[11] else None,
            "age_proof_available": bool(row[11] and os.path.isfile(row[11])),
            "status": row[12],
            "submitted_at": _format_date(row[13]),
            "decided_at": _format_date(row[14]),
            "decided_by": row[15],
            "audit_trail": [
                {
                    "at": _format_date(item[0]),
                    "action": item[1],
                    "actor": item[2],
                    "reason": item[3],
                }
                for item in audit
            ],
        })
    finally:
        conn.close()


@agent_api.post("/api/agent/officer/applications/<int:application_id>/decision")
def officer_decision(application_id):
    auth, error = _authorized("officer")
    if error:
        return error
    _, officer = auth
    data, error = _json_object()
    if error:
        return error
    decision = (data.get("decision") or "").strip().lower()
    reason = (data.get("reason") or "").strip()
    if decision not in ("approve", "reject"):
        return jsonify(error="decision must be approve or reject."), 400
    if not reason:
        return jsonify(error="A reason is required for every officer decision."), 400
    if len(reason) > 500:
        return jsonify(error="Decision reason must be 500 characters or fewer."), 400

    try:
        blocks = enabled_blocks()
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500
    status = "APPROVED" if decision == "approve" else "REJECTED"
    conn = portal.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE applications SET status = %s, decided_at = %s, decided_by = %s "
            "WHERE id = %s AND status = 'PENDING' AND block = ANY(%s) "
            "RETURNING application_no, mobile",
            (status, datetime.now(), officer, application_id, blocks),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return jsonify(
                error="Application is not pending or is outside the agent-enabled blocks."
            ), 409
        actor = "officer:%s" % officer
        portal.write_audit(cur, application_id, status, actor, reason)
        conn.commit()
    finally:
        conn.close()

    portal.send_sms(
        row[1],
        "Sewa Setu: application %s has been %s."
        % (row[0], status.lower()),
    )
    return jsonify({
        "application_number": row[0],
        "status": status,
        "decided_by": officer,
        "reason": reason,
    })
