"""
app.py — CSV Doctor Flask Application

Routes:
    GET  /                      Serve the single-page UI
    POST /api/analyze           Profile CSV + AI analysis
    POST /api/run-code          Execute cleaning code in sandbox
    GET  /api/download/<sid>    Download cleaned CSV
    POST /api/chat              Follow-up Q&A
"""

import os
import uuid
import tempfile
import json

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
)
from dotenv import load_dotenv

from backend.profiler import profile_csv
from backend.rulebook import retrieve_rules, load_rulebook
from backend.ai_engine import analyze_dataset, chat_followup
from backend.code_runner import run_cleaning_code

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

# Directory for storing per-session CSV data
SESSION_DIR = os.path.join(tempfile.gettempdir(), "csv_doctor_sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

# Pre-load the rulebook at startup
try:
    load_rulebook()
except Exception as e:
    print(f"Warning: Could not load rulebook: {e}")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _session_path(session_id: str, filename: str) -> str:
    """Return the path to a session file."""
    session_dir = os.path.join(SESSION_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return os.path.join(session_dir, filename)


def _save_session_data(session_id: str, csv_text: str, profile: dict) -> None:
    """Persist CSV text and profile to disk for later use."""
    with open(_session_path(session_id, "data.csv"), "w", encoding="utf-8") as f:
        f.write(csv_text)
    with open(_session_path(session_id, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f)


def _load_session_csv(session_id: str) -> str | None:
    """Load the CSV text for a session."""
    path = _session_path(session_id, "data.csv")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_session_profile(session_id: str) -> dict | None:
    """Load the profile dict for a session."""
    path = _session_path(session_id, "profile.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_cleaned_csv(session_id: str, cleaned_csv: str) -> None:
    """Save the cleaned CSV for download."""
    with open(_session_path(session_id, "cleaned.csv"), "w", encoding="utf-8") as f:
        f.write(cleaned_csv)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the single-page UI."""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Accept CSV data (file upload or JSON text), profile it, and run AI analysis.

    Accepts:
        - multipart/form-data with a 'file' field
        - application/json with a 'csv_text' field

    Returns:
        JSON: {session_id, profile, issues, cleaning_code, summary}
    """
    csv_text = None

    # --- Extract CSV text ---
    if request.content_type and "multipart/form-data" in request.content_type:
        if "file" not in request.files:
            return jsonify({"error": "No file provided."}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected."}), 400
        try:
            csv_text = file.read().decode("utf-8", errors="replace")
        except Exception as e:
            return jsonify({"error": f"Could not read file: {e}"}), 400
    else:
        data = request.get_json(silent=True) or {}
        csv_text = data.get("csv_text", "").strip()
        if not csv_text:
            return jsonify({"error": "No CSV data provided."}), 400

    # --- Profile the CSV ---
    profile = profile_csv(csv_text)
    if "error" in profile:
        return jsonify({"error": profile["error"]}), 422

    # --- Retrieve relevant rulebook rules ---
    # Build a query from column names and detected types
    query_parts = [col["name"] for col in profile.get("columns", [])]
    query_parts += [col["dtype"] for col in profile.get("columns", [])]
    query = " ".join(query_parts)
    rules = retrieve_rules(query, top_k=6)

    # --- AI analysis ---
    try:
        analysis = analyze_dataset(profile, rules)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    # --- Persist session data ---
    session_id = str(uuid.uuid4())
    _save_session_data(session_id, csv_text, profile)

    return jsonify({
        "session_id": session_id,
        "profile": profile,
        "issues": analysis.get("issues", []),
        "cleaning_code": analysis.get("cleaning_code", ""),
        "summary": analysis.get("summary", ""),
    })


@app.route("/api/run-code", methods=["POST"])
def run_code():
    """
    Execute the cleaning code against the session's CSV data.

    Accepts JSON: {session_id, code}

    Returns:
        JSON: {success, error, stdout, has_cleaned_csv}
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    code = data.get("code", "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required."}), 400
    if not code:
        return jsonify({"error": "No code provided."}), 400

    csv_text = _load_session_csv(session_id)
    if csv_text is None:
        return jsonify({"error": "Session not found. Please re-upload your CSV."}), 404

    result = run_cleaning_code(csv_text, code)

    if result["success"] and result.get("cleaned_csv"):
        _save_cleaned_csv(session_id, result["cleaned_csv"])

    return jsonify({
        "success": result["success"],
        "error": result.get("error"),
        "stdout": result.get("stdout", ""),
        "has_cleaned_csv": bool(result.get("cleaned_csv")),
    })


@app.route("/api/download/<session_id>")
def download(session_id: str):
    """
    Download the cleaned CSV for a session.
    """
    cleaned_path = _session_path(session_id, "cleaned.csv")
    if not os.path.exists(cleaned_path):
        return jsonify({"error": "No cleaned CSV available. Run the cleaning code first."}), 404

    return send_file(
        cleaned_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name="cleaned_data.csv",
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Handle a follow-up question about the dataset.

    Accepts JSON: {session_id, history, message}

    Returns:
        JSON: {reply}
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    history = data.get("history", [])
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Message cannot be empty."}), 400

    # Load profile for context (gracefully handle missing session)
    profile = {}
    if session_id:
        profile = _load_session_profile(session_id) or {}

    try:
        reply = chat_followup(profile, history, message)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    return jsonify({"reply": reply})


# ---------------------------------------------------------------------------
# Global error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error. Please try again."}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"CSV Doctor running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
