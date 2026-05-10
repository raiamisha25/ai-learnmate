from flask import Flask
from routes.main_routes import register_routes
from services.gemini_service import check_gemini_startup
from utils.error_handlers import register_error_handlers
from utils.template_filters import nl2br


def create_app():
    app = Flask(__name__)

    app.jinja_env.filters["nl2br"] = nl2br

    register_routes(app)
    register_error_handlers(app)

    return app


app = create_app()
check_gemini_startup()


if __name__ == "__main__":
    app.run(debug=False)
