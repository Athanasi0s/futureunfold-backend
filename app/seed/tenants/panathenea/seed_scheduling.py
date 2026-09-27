"""
Seed scheduling data for testing meeting endpoints.

Creates:
1. Dedicated meeting locations (rooms with nice names)
2. User agenda entries (to test conflict detection)
3. Sample meeting requests

Run with: python -m app.seed.seed_scheduling
Requires: seed_dummy_map, seed_users, seed_sessions to run first
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from app.db.session import SessionLocal
from app.models.user import User
from app.models.venue import Venue
from app.models.map_feature import MapFeature
from app.models.session import Session
from app.models.user_agenda import UserAgenda
from app.models.meeting import Meeting
from app.core.enums import MeetingStatus, UserRole


# Meeting location names to assign to existing rooms
MEETING_LOCATION_NAMES = [
    "AI Discovery Lounge (Hall A)",
    "Innovation Hub (Hall B)",
    "Networking Terrace",
    "Main Conference Room",
    "Startup Corner",
    "Investor Suite",
    "Tech Lab Alpha",
    "Creative Space Beta",
]


def seed_scheduling():
    """Seed scheduling-related data (idempotent)."""
    db = SessionLocal()

    try:
        print("🌱 Seeding scheduling data...")

        # ---------------------------
        # 1. UPDATE ROOM NAMES FOR MEETING LOCATIONS
        # ---------------------------
        rooms = db.execute(
            select(MapFeature)
            .where(MapFeature.feature_type == "room")
            .order_by(MapFeature.id)
            .limit(len(MEETING_LOCATION_NAMES))
        ).scalars().all()

        if not rooms:
            print("❌ No rooms found. Please run seed_dummy_map first.")
            return

        updated_rooms = 0
        for i, room in enumerate(rooms):
            if i < len(MEETING_LOCATION_NAMES):
                new_name = MEETING_LOCATION_NAMES[i]
                if room.name != new_name:
                    room.name = new_name
                    updated_rooms += 1

        db.commit()
        print(f"✅ Updated {updated_rooms} room names for meeting locations")

        # ---------------------------
        # 2. GET OR CREATE TEST USERS
        # ---------------------------
        # Get existing users
        users = db.execute(
            select(User).order_by(User.id).limit(10)
        ).scalars().all()

        if len(users) < 2:
            print("❌ Need at least 2 users. Please run seed_users first.")
            return

        print(f"✅ Found {len(users)} existing users")

        # Update some users to have complete profiles for testing
        test_profiles = [
            {
                "full_name": "Marcus Thorne",
                "company": "NexaSystems",
                "role": UserRole.speaker,
                "bio": "CTO with 15 years of experience in distributed systems",
                "avatar_url": "https://i.pravatar.cc/150?img=12",
            },
            {
                "full_name": "Elena Rodriguez",
                "company": "TechVentures",
                "role": UserRole.attendee,
                "bio": "Product Designer passionate about user experience",
                "avatar_url": "https://i.pravatar.cc/150?img=5",
            },
            {
                "full_name": "Alex Chen",
                "company": "CloudScale",
                "role": UserRole.speaker,
                "bio": "Cloud architect and open source contributor",
                "avatar_url": "https://i.pravatar.cc/150?img=8",
            },
            {
                "full_name": "Sofia Papadaki",
                "company": "GreenTech Solutions",
                "role": UserRole.exhibitor,
                "bio": "Sustainability expert and startup founder",
                "avatar_url": "https://i.pravatar.cc/150?img=9",
            },
        ]

        for i, profile in enumerate(test_profiles):
            if i < len(users):
                for key, value in profile.items():
                    setattr(users[i], key, value)

        db.commit()
        print(f"✅ Updated {min(len(test_profiles), len(users))} user profiles")

        # ---------------------------
        # 3. ADD SESSIONS TO USER AGENDAS
        # ---------------------------
        sessions = db.execute(
            select(Session).order_by(Session.start_time).limit(5)
        ).scalars().all()

        if not sessions:
            print("⚠️  No sessions found. Skipping agenda seeding.")
        else:
            # Add sessions to first user's agenda (for conflict testing)
            user1 = users[0]
            agenda_added = 0

            for session in sessions[:3]:  # Add first 3 sessions
                existing = db.execute(
                    select(UserAgenda).where(
                        UserAgenda.user_id == user1.id,
                        UserAgenda.session_id == session.id,
                    )
                ).scalar_one_or_none()

                if not existing:
                    agenda_item = UserAgenda(
                        user_id=user1.id,
                        session_id=session.id,
                    )
                    db.add(agenda_item)
                    agenda_added += 1

            # Add different sessions to second user's agenda
            if len(users) > 1:
                user2 = users[1]
                for session in sessions[1:4]:  # Add sessions 2-4
                    existing = db.execute(
                        select(UserAgenda).where(
                            UserAgenda.user_id == user2.id,
                            UserAgenda.session_id == session.id,
                        )
                    ).scalar_one_or_none()

                    if not existing:
                        agenda_item = UserAgenda(
                            user_id=user2.id,
                            session_id=session.id,
                        )
                        db.add(agenda_item)
                        agenda_added += 1

            db.commit()
            print(f"✅ Added {agenda_added} agenda entries for conflict testing")

        # ---------------------------
        # 4. CREATE SAMPLE MEETINGS
        # ---------------------------
        if len(users) >= 3:
            # Get a meeting location
            location = db.execute(
                select(MapFeature)
                .where(MapFeature.feature_type == "room")
                .limit(1)
            ).scalar_one_or_none()

            # Meeting 1: Pending request (user1 -> user2)
            base_date = datetime(2026, 5, 21, 14, 0, tzinfo=timezone.utc)

            existing_meeting = db.execute(
                select(Meeting).where(
                    Meeting.requester_id == users[0].id,
                    Meeting.recipient_id == users[1].id,
                    Meeting.status == MeetingStatus.pending,
                )
            ).scalar_one_or_none()

            if not existing_meeting:
                meeting1 = Meeting(
                    requester_id=users[0].id,
                    recipient_id=users[1].id,
                    proposed_start=base_date,
                    proposed_end=base_date + timedelta(minutes=30),
                    status=MeetingStatus.pending,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                    map_feature_id=location.id if location else None,
                    message="Would love to discuss the AI keynote with you!",
                )
                db.add(meeting1)
                print("✅ Created pending meeting request (user1 -> user2)")

            # Meeting 2: Confirmed meeting (user2 -> user3)
            if len(users) >= 3:
                existing_confirmed = db.execute(
                    select(Meeting).where(
                        Meeting.requester_id == users[1].id,
                        Meeting.recipient_id == users[2].id,
                        Meeting.status == MeetingStatus.confirmed,
                    )
                ).scalar_one_or_none()

                if not existing_confirmed:
                    meeting2 = Meeting(
                        requester_id=users[1].id,
                        recipient_id=users[2].id,
                        proposed_start=base_date + timedelta(hours=2),
                        proposed_end=base_date + timedelta(hours=2, minutes=30),
                        status=MeetingStatus.confirmed,
                        expires_at=None,  # Confirmed meetings don't expire
                        map_feature_id=location.id if location else None,
                        message="Let's talk about cloud architecture!",
                    )
                    db.add(meeting2)
                    print("✅ Created confirmed meeting (user2 -> user3)")

            db.commit()

        print("\n✅ Scheduling seed complete!")
        print("\n📌 Test the API:")
        print("   1. Login as a user first:")
        print("      POST http://127.0.0.1:8000/auth/login")
        print("   2. Get availability for user 2:")
        print("      GET http://127.0.0.1:8000/scheduling/availability/2")
        print("   3. Get meeting locations:")
        print("      GET http://127.0.0.1:8000/scheduling/locations?date=2026-05-21&time=14:00")
        print("   4. Get user's meetings:")
        print("      GET http://127.0.0.1:8000/scheduling/meetings")

    except Exception as e:
        print(f"❌ Error seeding scheduling data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


run = seed_scheduling

if __name__ == "__main__":
    run()
