import json
import os
from pathlib import Path

from flask import Blueprint, render_template_string

eval_dashboard_bp = Blueprint("eval_dashboard", __name__)

RESULTS_FILE = Path(
    os.getenv(
        "EVAL_RESULTS_FILE",
        "evals/results/results.json",
    )
)


@eval_dashboard_bp.get("/eval-dashboard")
def eval_dashboard():
    if RESULTS_FILE.exists():
        try:
            data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"evaluation_status": "unavailable", "results": []}
    else:
        data = {"evaluation_status": "not_run", "results": []}

    page = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Sewa Setu Evaluation Dashboard</title>
      <style>
        body { font-family: system-ui, sans-serif; max-width: 1100px;
               margin: 30px auto; padding: 0 16px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #f2f2f2; }
        .passed { color: #176b35; font-weight: 700; }
        .failed { color: #a12622; font-weight: 700; }
        .not_run { color: #715a00; font-weight: 700; }
        pre { white-space: pre-wrap; overflow-wrap: anywhere; }
      </style>
    </head>
    <body>
      <h1>Sewa Setu Evaluation Dashboard</h1>
      <p>Overall status: <strong>{{ data.get("evaluation_status", "unknown") }}</strong></p>
      <p>{{ data.get("note", "Results are based on the saved evaluation file.") }}</p>
      {% set results = data.get("results", []) %}
      {% set passed_count = results | selectattr("status", "equalto", "passed") | list | length %}
      {% set failed_count = results | selectattr("status", "equalto", "failed") | list | length %}
      {% set completed_count = passed_count + failed_count %}
      {% if completed_count %}
      <p>Persona pass rate: {{ passed_count }}/{{ completed_count }}
         ({{ (100 * passed_count / completed_count) | round(1) }}%).</p>
      {% else %}
      <p>Persona pass rate: not available until evaluations have run.</p>
      {% endif %}
      <table>
        <thead>
          <tr>
            <th>Citizen</th>
            <th>Goal</th>
            <th>Status</th>
            <th>Conversation and checks</th>
          </tr>
        </thead>
        <tbody>
        {% for item in data.get("results", []) %}
          <tr>
            <td>
              <strong>{{ item.get("persona_name", item.get("persona_id", "")) }}</strong><br>
              Age {{ item.get("age", "-") }}; {{ item.get("village", "-") }},
              {{ item.get("block", "-") }}<br>
              {{ item.get("how_they_talk", "") }}
            </td>
            <td>{{ item.get("goal", "") }}</td>
            <td class="{{ item.get('status', 'unknown') }}">{{ item.get("status", "unknown") }}</td>
            <td><pre>{{ item | tojson(indent=2) }}</pre></td>
          </tr>
        {% else %}
          <tr><td colspan="4">No evaluation results have been recorded.</td></tr>
        {% endfor %}
        </tbody>
      </table>
      <p>Generated at: {{ data.get("generated_at", "Not available") }}</p>
    </body>
    </html>
    """
    return render_template_string(page, data=data)