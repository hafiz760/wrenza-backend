"""Template rendering for emails.

Each message is a pair: an HTML template and a plain-text one. Both are
required — a multipart message reads in any client and scores better with spam
filters than HTML alone.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_settings

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Two environments, because the whitespace rules differ. `trim_blocks` and
# `lstrip_blocks` keep generated HTML tidy, but in a plain-text email they eat
# the newlines and indentation that carry the layout.
_html_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# No autoescape: escaping here would put &amp; into a plain-text email.
_text_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=False,
    keep_trailing_newline=True,
)


def money(amount: float, currency: str = "PKR") -> str:
    """Format a price the way the storefront does."""
    symbol = "Rs." if currency == "PKR" else currency
    return f"{symbol} {amount:,.0f}"


for _env in (_html_env, _text_env):
    _env.filters["money"] = money


def render(template: str, /, **context) -> tuple[str, str]:
    """Render one email, returning `(html, text)`.

    `template` is the stem — `order_confirmation` loads both
    `order_confirmation.html` and `order_confirmation.txt`.

    Positional-only, so a template can use `name` as a context variable. The
    contact form does exactly that, and without the `/` it collided with this
    parameter.
    """
    settings = get_settings()
    shared = {
        "frontend_url": settings.FRONTEND_URL.rstrip("/"),
        "dashboard_url": settings.DASHBOARD_URL.rstrip("/"),
        "logo_url": settings.EMAIL_LOGO_URL,
        "logo_width": settings.EMAIL_LOGO_WIDTH,
        **context,
    }

    html = _html_env.get_template(f"{template}.html").render(**shared)
    text = _text_env.get_template(f"{template}.txt").render(**shared)
    return html, text
