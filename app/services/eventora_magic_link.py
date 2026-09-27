from __future__ import annotations

from dataclasses import dataclass

from jose import JWTError, jwt


class EventoraTokenError(ValueError):
    pass


@dataclass(frozen=True)
class EventoraInvitation:
    subject: str
    jti: str
    email: str
    full_name: str
    qr_code: str
    invitation_id: str


def decode_eventora_invitation(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
) -> EventoraInvitation:
    """Verify and normalize a signed EVENTORA one-time invitation token."""
    if not secret:
        raise EventoraTokenError("EVENTORA integration is not configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise EventoraTokenError("Invalid or expired EVENTORA token") from exc

    required = {
        "sub": payload.get("sub"),
        "jti": payload.get("jti"),
        "email": payload.get("email"),
        "full_name": payload.get("full_name") or payload.get("name"),
        "qr_code": payload.get("qr_code"),
        "invitation_id": payload.get("invitation_id"),
    }
    if any(not isinstance(value, str) or not value.strip() for value in required.values()):
        raise EventoraTokenError("EVENTORA token is missing required claims")

    email = required["email"].strip().lower()
    if "@" not in email or len(email) > 320:
        raise EventoraTokenError("EVENTORA token contains an invalid email")

    return EventoraInvitation(
        subject=required["sub"].strip(),
        jti=required["jti"].strip(),
        email=email,
        full_name=required["full_name"].strip(),
        qr_code=required["qr_code"].strip(),
        invitation_id=required["invitation_id"].strip(),
    )
