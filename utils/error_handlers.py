from flask import render_template

from utils.errors import AppError


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(error):
        return render_template("error.html", message=error.message), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return (
            render_template(
                "error.html",
                message="That page does not exist. Use the navigation above to continue.",
            ),
            404,
        )

    @app.errorhandler(500)
    def handle_server_error(_error):
        return (
            render_template(
                "error.html",
                message="Something went wrong. Please try again in a moment.",
            ),
            500,
        )

