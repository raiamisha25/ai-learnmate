from markupsafe import Markup, escape


def nl2br(value):
    """Keep beginner-friendly generated text readable in HTML."""
    return Markup("<br>".join(escape(value or "").splitlines()))
