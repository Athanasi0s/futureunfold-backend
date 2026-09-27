from __future__ import annotations

import re
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.session import Session
from app.models.session_speaker import SessionSpeaker
from app.models.speaker import Speaker
from app.models.user import User


ATHENS = ZoneInfo("Europe/Athens")

SPEAKERS = {
    "Vassilis Kazas": "Managing Partner, Grant Thornton",
    "Kyriakos Pierrakakis": "Minister of Economy and Finance of the Hellenic Republic & President of the Eurogroup",
    "Stella Angelopoulou": "Partner, Head of Technology, Grant Thornton",
    "Spyros Theodoropoulos": (
        "President & CEO, Bespoke SGA Holdings S.A. & Chairman of the Board "
        "of Directors of SEV Hellenic Federation of Enterprises"
    ),
    "Agapi Sbokou": "President, SETE & CEO, PHĀEA",
    "Theodoros Fessas": "Chairman Quest Group, Quest Holdings",
    "Minas Liarokapis": "CEO, Acumino Inc (tbc)",
    "Stratos Molyviatis": "Group Chief Operating Officer at National Bank of Greece (tbc)",
    "Vardis Vardinogiannis": "CEO, Couch Heroes (tbc)",
    "Speaker 1": "E80 Group (tbc)",
    "Kyriakos Mitsotakis": "Prime Minister of Greece (tbc)",
    "Dr. Nikolaos Karamouzis": "President, Grant Thornton Consulting",
}

SESSIONS = [
    ("18:00", "18:30", "Welcome", "opening", []),
    ("18:30", "18:40", "CEO Welcome", "keynote", ["Vassilis Kazas"]),
    ("18:40", "18:55", "Opening Address", "keynote", ["Kyriakos Pierrakakis"]),
    (
        "18:55",
        "19:10",
        "Technology & Beyond: The Future Advantage",
        "keynote",
        ["Stella Angelopoulou"],
    ),
    (
        "19:10",
        "19:45",
        "Discussion Circle: “Accelerating Greek Entrepreneurship | The Next AI Frontier”",
        "panel",
        ["Spyros Theodoropoulos", "Agapi Sbokou", "Theodoros Fessas"],
    ),
    (
        "19:45",
        "20:00",
        "Future Advantage | Industry Insight by: (Video Address)",
        "video",
        ["Minas Liarokapis", "Stratos Molyviatis", "Vardis Vardinogiannis", "Speaker 1"],
    ),
    (
        "20:00",
        "20:30",
        "Discussion with Prime Minister Kyriakos Mitsotakis on AI, People and the Future of Society",
        "panel",
        ["Kyriakos Mitsotakis", "Dr. Nikolaos Karamouzis", "Vassilis Kazas"],
    ),
    ("20:30", "21:30", "Cocktail", "networking", []),
]


def _email_for(name: str) -> str:
    # Keep the existing identity when correcting the spelling of Fessas’s name.
    legacy_name = "Theodore Fessas" if name == "Theodoros Fessas" else name
    slug = re.sub(r"[^a-z0-9]+", ".", legacy_name.lower()).strip(".")
    return f"speaker+{slug}@future-unfold.invalid"


def _at(time_text: str) -> datetime:
    hour, minute = (int(part) for part in time_text.split(":"))
    return datetime(2026, 11, 24, hour, minute, tzinfo=ATHENS)


def run() -> None:
    db = SessionLocal()
    try:
        users: dict[str, User] = {}
        for name, role_title in SPEAKERS.items():
            email = _email_for(name)
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(
                    email=email,
                    password_hash=hash_password(secrets.token_urlsafe(48)),
                    full_name=name,
                    role=UserRole.speaker,
                    company=role_title,
                )
                db.add(user)
                db.flush()
            else:
                user.full_name = name
                user.role = UserRole.speaker
                user.company = role_title
            if db.query(Speaker).filter(Speaker.user_id == user.id).first() is None:
                db.add(Speaker(user_id=user.id))
            users[name] = user

        for start, end, title, session_type, speaker_names in SESSIONS:
            session = db.query(Session).filter(Session.start_time == _at(start)).first()
            if session is None:
                session = Session(
                    title=title,
                    start_time=_at(start),
                    end_time=_at(end),
                    type=session_type,
                )
                db.add(session)
                db.flush()
            else:
                session.title = title
                session.start_time = _at(start)
                session.end_time = _at(end)
                session.type = session_type

            db.query(SessionSpeaker).filter(
                SessionSpeaker.session_id == session.id
            ).delete(synchronize_session=False)
            for name in speaker_names:
                db.add(SessionSpeaker(session_id=session.id, user_id=users[name].id))

        db.commit()
        print("Future Unfold speakers and official 24 November agenda seeded")
    finally:
        db.close()
