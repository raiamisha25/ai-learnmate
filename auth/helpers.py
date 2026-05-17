from functools import wraps

from flask import g, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import find_user_by_email, find_user_by_id


def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = find_user_by_id(user_id) if user_id else None


def login_user(user, remember=False):
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = bool(remember)


def logout_user():
    session.clear()


def authenticate_user(email, password):
    user = find_user_by_email(email)

    if user and check_password_hash(user["password_hash"], password):
        return user

    return None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login", next=request.path))

        return view(*args, **kwargs)

    return wrapped_view

