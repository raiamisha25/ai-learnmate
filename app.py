import os
from datetime import timedelta

from flask import Flask
from dotenv import load_dotenv

from auth.helpers import load_logged_in_user
from database.db import init_db
from routes.main_routes import register_routes
from services.gemini_service import check_gemini_startup
from utils.error_handlers import register_error_handlers
from utils.template_filters import nl2br


load_dotenv()


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.permanent_session_lifetime = timedelta(days=30)

    app.jinja_env.filters["nl2br"] = nl2br

    init_db()

    app.before_request(load_logged_in_user)

    register_routes(app)
    register_error_handlers(app)

    return app


app = create_app()
check_gemini_startup()


if __name__ == "__main__":
    app.run(debug=False)
