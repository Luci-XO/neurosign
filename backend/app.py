"""app.py - NeuroSign Flask backend. Run: python app.py  (serves 127.0.0.1 only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so imports work from any cwd

from flask import Flask, jsonify
from flask_cors import CORS

import config
from db import init_db
from routes.assessments import assessments_bp
from routes.steps import steps_bp
from routes.report import report_bp


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 MB cap on uploads
    CORS(app)
    for bp in (assessments_bp, steps_bp, report_bp):
        app.register_blueprint(bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "neurosign-backend"})

    @app.errorhandler(Exception)
    def unexpected(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        app.logger.exception("Unhandled error")
        return jsonify({"error": "Unexpected server error. See the terminal for details."}), 500

    return app


if __name__ == "__main__":
    init_db()
    print(f"[app] NeuroSign backend on http://127.0.0.1:{config.PORT}", flush=True)
    # use_reloader=False: the reloader spawns a second process that Electron cannot stop cleanly
    create_app().run(host="127.0.0.1", port=config.PORT, debug=config.DEBUG, use_reloader=False)