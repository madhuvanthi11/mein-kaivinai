"""Authentication and authorisation.

Two things matter here and both are enforced on the server:

1. **Identity.** A Firebase ID token is verified against Google's published
   signing certificates. Verification needs only the project id -- no
   service-account key -- so it works with the client config the user already
   has. An unverifiable token is rejected; it is never trusted on its face.

2. **Role and jurisdiction.** Roles are assigned out of band (Firebase custom
   claims set by an administrator, or a server-side registry file). A user can
   never grant themselves a role, and every privileged route re-checks both the
   role and the jurisdiction on every request. Hiding a button in the frontend
   is not access control and is never relied upon.

Development mode
----------------
With `DEV_AUTH=1` the server accepts an unsigned `X-Dev-User` header so the
workflow can be exercised offline and in tests. This is insecure by design and
`/api/status` reports `auth.mode = "dev-insecure"` so it cannot be mistaken for
a real deployment.
"""
import json
import os
import time
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException

from .. import config

CITIZEN = "citizen"
ADMIN = "admin"
GOVERNMENT = "government"
ROLES = (CITIZEN, ADMIN, GOVERNMENT)

ALL_JURISDICTIONS = "all"


@dataclass(frozen=True)
class Principal:
    uid: str
    role: str = CITIZEN
    email: str | None = None
    name: str | None = None
    # City names this officer may act on, or ["all"] for state level.
    jurisdiction: list = field(default_factory=list)
    source: str = "unverified"

    def covers(self, city: str | None) -> bool:
        if self.role == CITIZEN:
            return False
        if ALL_JURISDICTIONS in self.jurisdiction:
            return True
        if city is None:
            return False
        return any(j.lower() == city.lower() for j in self.jurisdiction)

    def public(self) -> dict:
        return {"uid": self.uid, "role": self.role, "email": self.email,
                "name": self.name, "jurisdiction": self.jurisdiction,
                "auth_source": self.source}


# ----------------------------------------------------------------- role registry
_registry_cache = {"mtime": None, "data": {"admin_users": {}, "government_users": {}}}


def role_registry() -> dict:
    """Out-of-band role assignments read from a server-side JSON file.

    Reloaded when the file changes so an officer can be added without a restart.
    """
    path = config.ROLE_REGISTRY_PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _registry_cache["data"]
    if _registry_cache["mtime"] == mtime:
        return _registry_cache["data"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return _registry_cache["data"]
    data = {"admin_users": raw.get("admin_users", {}) or {},
            "government_users": raw.get("government_users", {}) or {}}
    _registry_cache.update({"mtime": mtime, "data": data})
    return data


def _lookup(uid: str, email: str | None) -> tuple[str, list] | None:
    reg = role_registry()
    for collection, role in (("government_users", GOVERNMENT), ("admin_users", ADMIN)):
        table = reg[collection]
        entry = table.get(uid) or (table.get(email.lower()) if email else None)
        if entry:
            j = entry.get("jurisdiction") or []
            return role, ([j] if isinstance(j, str) else list(j))
    return None


def resolve_role(claims: dict) -> tuple[str, list]:
    """Custom claims first, then the server-side registry, else citizen."""
    claim_role = (claims.get("role") or "").lower()
    if claim_role in (ADMIN, GOVERNMENT):
        j = claims.get("jurisdiction") or []
        return claim_role, ([j] if isinstance(j, str) else list(j))
    found = _lookup(claims.get("uid") or claims.get("sub") or "",
                    (claims.get("email") or "").lower() or None)
    if found:
        return found
    return CITIZEN, []


# ----------------------------------------------------------- firebase verification
_jwks = {"fetched": 0.0, "keys": {}}
JWKS_TTL = 3600


def _certs() -> dict:
    """Google's current x509 signing certificates, cached for an hour."""
    import httpx
    if _jwks["keys"] and time.time() - _jwks["fetched"] < JWKS_TTL:
        return _jwks["keys"]
    with httpx.Client(timeout=config.HTTP_TIMEOUT) as c:
        r = c.get(config.FIREBASE_JWKS_URL)
        r.raise_for_status()
        _jwks.update({"fetched": time.time(), "keys": r.json()})
    return _jwks["keys"]


class AuthError(Exception):
    pass


def verify_firebase_token(token: str) -> dict:
    """Verify signature, audience, issuer and expiry. Raises on any failure."""
    if not config.FIREBASE_AUTH_CONFIGURED:
        raise AuthError("Firebase project id is not configured on the server.")
    try:
        import jwt
        from cryptography.x509 import load_pem_x509_certificate
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise AuthError("Token verification libraries are not installed.") from exc

    try:
        kid = jwt.get_unverified_header(token).get("kid")
        certs = _certs()
        pem = certs.get(kid)
        if not pem:
            raise AuthError("Signing key not recognised.")
        public_key = load_pem_x509_certificate(pem.encode()).public_key()
        claims = jwt.decode(
            token, public_key, algorithms=["RS256"],
            audience=config.FIREBASE_PROJECT_ID,
            issuer=config.FIREBASE_ISSUER + config.FIREBASE_PROJECT_ID,
        )
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"Token rejected: {exc}") from exc
    if not claims.get("sub"):
        raise AuthError("Token carries no subject.")
    return claims


def _dev_principal(header: str) -> Principal:
    """`X-Dev-User: uid|role|City,City|Display Name`. Demo identity mode only."""
    parts = [p.strip() for p in header.split("|")]
    uid = parts[0] or "dev-user"
    role = (parts[1].lower() if len(parts) > 1 and parts[1] else CITIZEN)
    if role not in ROLES:
        role = CITIZEN
    jur = [j.strip() for j in parts[2].split(",")] if len(parts) > 2 and parts[2] else []
    if role != CITIZEN and not jur:
        jur = [ALL_JURISDICTIONS]
    display = parts[3] if len(parts) > 3 and parts[3] else uid
    return Principal(uid=uid, role=role, email=None,
                     name=display, jurisdiction=jur, source="demo-identity")


# ------------------------------------------------------------------ dependencies
async def optional_user(authorization: str | None = Header(default=None),
                        x_dev_user: str | None = Header(default=None)) -> Principal | None:
    """The caller if they presented valid credentials, otherwise None.

    Used by routes that are readable anonymously (issued public advisories)
    but that behave differently for a signed-in user.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = verify_firebase_token(token)
        except AuthError:
            return None
        role, jur = resolve_role(claims)
        return Principal(uid=claims["sub"], role=role, email=claims.get("email"),
                         name=claims.get("name") or claims.get("email"),
                         jurisdiction=jur, source="firebase")
    if x_dev_user and config.DEV_AUTH:
        return _dev_principal(x_dev_user)
    return None


async def current_user(authorization: str | None = Header(default=None),
                       x_dev_user: str | None = Header(default=None)) -> Principal:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = verify_firebase_token(token)
        except AuthError as exc:
            raise HTTPException(401, str(exc))
        role, jur = resolve_role(claims)
        return Principal(uid=claims["sub"], role=role, email=claims.get("email"),
                         name=claims.get("name") or claims.get("email"),
                         jurisdiction=jur, source="firebase")
    if x_dev_user:
        if not config.DEV_AUTH:
            raise HTTPException(
                401, "Demo identities are disabled on this server. Sign in with a "
                     "verified account.")
        return _dev_principal(x_dev_user)
    raise HTTPException(401, "Sign-in required.")


def require_role(*allowed: str):
    """403 on role violation, regardless of what the frontend displayed."""
    async def dep(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in allowed:
            raise HTTPException(
                403, f"This action requires the {' or '.join(allowed)} role. "
                     f"Your account has the {user.role} role.")
        return user
    return dep


require_admin = require_role(ADMIN)
require_government = require_role(GOVERNMENT)
require_officer = require_role(ADMIN, GOVERNMENT)


def assert_jurisdiction(user: Principal, city: str | None) -> None:
    if not user.covers(city):
        raise HTTPException(
            403, f"{city or 'That area'} is outside your assigned jurisdiction "
                 f"({', '.join(user.jurisdiction) or 'none'}).")


def status() -> dict:
    # The weakest accepted credential decides the mode, not the strongest.
    mode = ("demo-identity" if config.DEV_AUTH
            else "firebase" if config.FIREBASE_AUTH_CONFIGURED else "disabled")
    reg = role_registry()
    return {
        "mode": mode,
        "verified_tokens_accepted": config.FIREBASE_AUTH_CONFIGURED,
        "demo_identities_accepted": config.DEV_AUTH,
        "roles_enforced_server_side": True,
        "firebase_project_configured": config.FIREBASE_AUTH_CONFIGURED,
        "dev_auth_enabled": config.DEV_AUTH,
        "token_verification": ("Firebase ID token, RS256, verified against Google "
                               "public certificates" if config.FIREBASE_AUTH_CONFIGURED
                               else "Not available - no FIREBASE_PROJECT_ID set"),
        "role_source": "Firebase custom claims, then server-side role registry",
        "registered_admins": len(reg["admin_users"]),
        "registered_government_users": len(reg["government_users"]),
        "warning": ("Demo identity mode is on. Anyone can claim any role, because "
                    "the identity behind it is asserted by the client rather than "
                    "proved. Role and jurisdiction rules are still enforced on every "
                    "request. Set DEV_AUTH=0 to require verified sign-in. "
                    "Do not run this way in production.") if config.DEV_AUTH else None,
    }
