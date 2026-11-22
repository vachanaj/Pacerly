import os
from uuid import UUID
from typing import List
from functools import lru_cache

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# External issuer URL embedded in JWT "iss" claim
KEYCLOAK_ISSUER_URL = os.getenv(
    "KEYCLOAK_ISSUER_URL",
    "https://group-4-m7011e-ltu.se/auth/realms/pacerly",
)

# Internal Kubernetes Service DNS for fast JWKS public key retrieval
KEYCLOAK_INTERNAL_JWKS_URL = os.getenv(
    "KEYCLOAK_INTERNAL_JWKS_URL",
    "http://keycloak.pacerly-app.svc.cluster.local:8080/auth/realms/pacerly/protocol/openid-connect/certs",
)

bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedUser(BaseModel):
    """Maps directly to the `user_profiles` table keys."""
    user_id: UUID          # Matches user_profiles.user_id (PK)
    email: str             # Matches user_profiles.email (UK)
    display_name: str      # Matches user_profiles.display_name
    roles: List[str] = []


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient:
    return PyJWKClient(KEYCLOAK_INTERNAL_JWKS_URL, cache_keys=True, lifespan=3600)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    token = credentials.credentials
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER_URL,
            options={"verify_aud": False},  # Public SPA tokens use azp="pacerly-frontend"
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
        )

    try:
        user_uuid = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject (sub) is missing or not a valid UUID",
        )

    roles = payload.get("realm_access", {}).get("roles", [])
    email = payload.get("email", "")
    display_name = (
        payload.get("name")
        or payload.get("preferred_username")
        or email.split("@")[0]
    )

    return AuthenticatedUser(
        user_id=user_uuid,
        email=email,
        display_name=display_name,
        roles=roles,
    )


def require_role(required_role: str):
    """Dependency factory enforcing RBAC (e.g., Depends(require_role('admin')))."""
    def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if required_role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_role}' role",
            )
        return user
    return role_checker