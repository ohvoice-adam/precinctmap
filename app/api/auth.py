"""Admin authentication. The map is public; only ingest (and the admin page) need a login.

HTTP Basic, credentials from PRECINCTMAP_ADMIN_USER / PRECINCTMAP_ADMIN_PASSWORD. Fails closed:
with no password, or a placeholder one, every admin request is refused. State-changing requests
must also send `X-PRECINCTMAP-Admin: 1`; browsers re-send cached Basic credentials on cross-site
form posts, and a custom header cannot be added cross-site without CORS (which is off).
Serve over HTTPS (reverse proxy) before exposing beyond localhost: Basic auth is plaintext.
"""

import logging
import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

log = logging.getLogger("precinctmap.api.auth")

PLACEHOLDERS = frozenset({"", "changeme", "password", "admin"})
CSRF_HEADER = "x-precinctmap-admin"
_basic = HTTPBasic(realm="precinctmap admin", auto_error=False)


def _configured() -> tuple[str, str] | None:
    user = os.environ.get("PRECINCTMAP_ADMIN_USER", "admin")
    password = os.environ.get("PRECINCTMAP_ADMIN_PASSWORD", "")
    if password.lower() in PLACEHOLDERS or len(password) < 12:
        return None
    return user, password


def _challenge(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Basic realm="precinctmap admin"'},
    )


def require_admin(
    request: Request, credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)]
) -> str:
    expected = _configured()
    if expected is None:
        log.error("admin request refused: PRECINCTMAP_ADMIN_PASSWORD is unset or a placeholder")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Admin login is not configured: "
            "set PRECINCTMAP_ADMIN_PASSWORD (12+ characters) in .env",
        )
    if credentials is None:
        raise _challenge("Admin login required")
    user_ok = secrets.compare_digest(credentials.username.encode(), expected[0].encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), expected[1].encode())
    if not (user_ok and pass_ok):
        log.warning("failed admin login for %r from %s", credentials.username, request.client)
        raise _challenge("Wrong user name or password")
    if request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing X-PRECINCTMAP-Admin header")
    return credentials.username


AdminUser = Annotated[str, Depends(require_admin)]
