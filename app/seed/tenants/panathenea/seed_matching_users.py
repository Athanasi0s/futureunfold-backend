# app/seed/seed_matching_users.py
# Seed dummy users with full onboarding data for testing the matching endpoint.
# Also seeds scheduling data (meetings, agenda entries) for these users.

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.db.session import SessionLocal
from app.models.user import User
from app.models.interest import Interest
from app.models.user_interest import UserInterest
from app.models.goal import Goal
from app.models.user_goal import UserGoal
from app.models.user_onboarding import UserOnboarding
from app.models.meeting import Meeting
from app.models.session import Session
from app.models.user_agenda import UserAgenda
from app.models.map_feature import MapFeature
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.session_speaker import SessionSpeaker
from app.models.venue import Venue
from app.core.security import hash_password
from app.core.enums import MeetingStatus, OnboardingStatus, ExperienceLevel, DiscussionTopic, UserRole


DUMMY_USERS = [
    {
        "email": "alice@test.com",
        "full_name": "Alice Johnson",
        "role": UserRole.speaker,
        "company": "AI Labs Inc.",
        "bio": "AI researcher and speaker focused on machine learning applications.",
        "interests": ["AI & Machine Learning", "Data Science", "Cloud Computing", "Robotics", "IoT"],
        "goals": ["Find co-founders", "Get funding"],
        "groups": ["ai_deeptech", "cloud_cyber"],  # Common with test user
        "experience_level": ExperienceLevel.experienced,
        "discussion_topics": [DiscussionTopic.fundraising, DiscussionTopic.product_market_fit],
    },
    {
        "email": "bob@test.com",
        "full_name": "Bob Smith",
        "role": UserRole.attendee,
        "company": "FinTech Solutions",
        "bio": "Blockchain enthusiast exploring decentralized finance.",
        "interests": ["Blockchain", "FinTech", "Cybersecurity", "Cloud Computing"],
        "goals": ["Expand network", "Find mentors"],
        "groups": ["blockchain_web3", "cloud_cyber"],  # cloud_cyber common with test user
        "experience_level": ExperienceLevel.early_stage,
        "discussion_topics": [DiscussionTopic.fundraising],
    },
    {
        "email": "charlie@test.com",
        "full_name": "Charlie Brown",
        "role": UserRole.attendee,
        "company": "GameDev Studio",
        "bio": "Game developer passionate about VR/AR experiences.",
        "interests": ["Gaming", "VR/AR", "Mobile Development", "Web Development"],
        "goals": ["Learn new skills", "Expand network"],
        "groups": ["smart_city_mobility"],  # No common groups with test user
        "experience_level": ExperienceLevel.beginner,
        "discussion_topics": [DiscussionTopic.scaling_teams],
    },
    {
        "email": "diana@test.com",
        "full_name": "Diana Prince",
        "role": UserRole.speaker,
        "company": "Quantum Dynamics",
        "bio": "Quantum computing pioneer and robotics expert.",
        "interests": ["AI & Machine Learning", "Quantum Computing", "Robotics", "Data Science", "Cybersecurity"],
        "goals": ["Find co-founders", "Find talent"],
        "groups": ["ai_deeptech", "women_in_tech"],  # ai_deeptech common with test user
        "experience_level": ExperienceLevel.expert,
        "discussion_topics": [DiscussionTopic.scaling_teams, DiscussionTopic.product_market_fit],
    },
]

# A test user you can log in as to test matching
TEST_USER = {
    "email": "testmatch@test.com",
    "full_name": "Test Matcher",
    "password": "test1234",
    "role": UserRole.attendee,
    "company": "TestCorp",
    "bio": "Testing matching features.",
    "interests": ["AI & Machine Learning", "Data Science", "Cloud Computing", "Robotics", "Open Source"],
    "goals": ["Find co-founders", "Get funding", "Expand network"],
    "groups": ["ai_deeptech", "cloud_cyber"],  # Common with alice & diana (ai_deeptech), bob (cloud_cyber)
    "experience_level": ExperienceLevel.early_stage,
    "discussion_topics": [DiscussionTopic.fundraising, DiscussionTopic.product_market_fit],
}

# Sessions for speaker users
SPEAKER_SESSIONS = [
    {
        "speaker_email": "alice@test.com",
        "title": "Introduction to Machine Learning",
        "description": "A comprehensive introduction to ML concepts and practical applications.",
        "type": "workshop",
        "duration_minutes": 60,
    },
    {
        "speaker_email": "alice@test.com",
        "title": "AI Ethics and Responsible Development",
        "description": "Discussing ethical considerations in AI development.",
        "type": "talk",
        "duration_minutes": 45,
    },
    {
        "speaker_email": "diana@test.com",
        "title": "Quantum Computing Fundamentals",
        "description": "Understanding the basics of quantum computing and its future.",
        "type": "keynote",
        "duration_minutes": 60,
    },
    {
        "speaker_email": "diana@test.com",
        "title": "Robotics in Modern Industry",
        "description": "How robotics is transforming manufacturing and beyond.",
        "type": "workshop",
        "duration_minutes": 90,
    },
]


def main():
    db: DBSession = SessionLocal()
    try:
        # Fetch interests and goals from DB
        interests = db.query(Interest).all()
        if not interests:
            print("No interests found. Run seed_interests first: python -m app.seed.seed_interests")
            return

        goals = db.query(Goal).all()
        if not goals:
            print("No goals found. Run seed_goals first: python -m app.seed.seed_goals")
            return

        interest_map = {i.name: i.id for i in interests}
        goal_map = {g.name: g.id for g in goals}

        # Fetch groups from DB
        groups = db.query(Group).all()
        group_map = {g.ref_key: g.id for g in groups}

        created_users = 0
        created_interest_links = 0
        created_goal_links = 0
        created_group_links = 0
        created_onboarding = 0

        # Seed test user and dummy users
        all_users = [TEST_USER] + DUMMY_USERS
        for user_data in all_users:
            existing = db.query(User).filter(User.email == user_data["email"]).first()
            if existing:
                user = existing
                # Update existing user with new fields
                user.role = user_data.get("role", UserRole.attendee)
                user.company = user_data.get("company")
                user.bio = user_data.get("bio")
            else:
                user = User(
                    email=user_data["email"],
                    full_name=user_data.get("full_name"),
                    password_hash=hash_password(user_data.get("password", "password123")),
                    role=user_data.get("role", UserRole.attendee),
                    company=user_data.get("company"),
                    bio=user_data.get("bio"),
                )
                db.add(user)
                db.flush()
                created_users += 1

            # Add interests
            for interest_name in user_data["interests"]:
                interest_id = interest_map.get(interest_name)
                if not interest_id:
                    print(f"  Warning: interest '{interest_name}' not found in DB, skipping.")
                    continue
                exists = (
                    db.query(UserInterest)
                    .filter(UserInterest.user_id == user.id, UserInterest.interest_id == interest_id)
                    .first()
                )
                if not exists:
                    db.add(UserInterest(user_id=user.id, interest_id=interest_id))
                    created_interest_links += 1

            # Add goals
            for goal_name in user_data["goals"]:
                goal_id = goal_map.get(goal_name)
                if not goal_id:
                    print(f"  Warning: goal '{goal_name}' not found in DB, skipping.")
                    continue
                exists = (
                    db.query(UserGoal)
                    .filter(UserGoal.user_id == user.id, UserGoal.goal_id == goal_id)
                    .first()
                )
                if not exists:
                    db.add(UserGoal(user_id=user.id, goal_id=goal_id))
                    created_goal_links += 1

            # Add groups
            for group_ref_key in user_data.get("groups", []):
                group_id = group_map.get(group_ref_key)
                if not group_id:
                    print(f"  Warning: group '{group_ref_key}' not found in DB, skipping.")
                    continue
                exists = (
                    db.query(GroupMember)
                    .filter(GroupMember.user_id == user.id, GroupMember.group_id == group_id)
                    .first()
                )
                if not exists:
                    db.add(GroupMember(user_id=user.id, group_id=group_id))
                    created_group_links += 1

            # Create or update onboarding record
            onboarding = db.query(UserOnboarding).filter(
                UserOnboarding.user_id == user.id
            ).first()

            discussion_topics_str = [t.value for t in user_data["discussion_topics"]]

            if not onboarding:
                onboarding = UserOnboarding(
                    user_id=user.id,
                    experience_level=user_data["experience_level"],
                    discussion_topics=discussion_topics_str,
                    status=OnboardingStatus.completed,
                    completed_at=datetime.now(timezone.utc),
                )
                db.add(onboarding)
                created_onboarding += 1
            else:
                onboarding.experience_level = user_data["experience_level"]
                onboarding.discussion_topics = discussion_topics_str
                onboarding.status = OnboardingStatus.completed
                onboarding.completed_at = datetime.now(timezone.utc)

        db.commit()
        print(f"Seed matching users done.")
        print(f"  Created {created_users} users")
        print(f"  Created {created_interest_links} interest links")
        print(f"  Created {created_goal_links} goal links")
        print(f"  Created {created_group_links} group memberships")
        print(f"  Created {created_onboarding} onboarding records")
        print(f"\nTest user credentials:")
        print(f"  Email: {TEST_USER['email']}")
        print(f"  Password: {TEST_USER['password']}")

        # ---------------------------
        # SPEAKER SESSIONS
        # ---------------------------
        print("\nSeeding sessions for speaker users...")

        # Get a venue for the sessions
        venue = db.execute(select(Venue).limit(1)).scalar_one_or_none()

        # Base date for sessions
        session_base_date = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
        sessions_created = 0

        for i, session_data in enumerate(SPEAKER_SESSIONS):
            speaker_email = session_data["speaker_email"]
            speaker = db.query(User).filter(User.email == speaker_email).first()
            if not speaker:
                print(f"  Warning: speaker '{speaker_email}' not found, skipping session.")
                continue

            # Check if session already exists by title
            existing_session = db.query(Session).filter(
                Session.title == session_data["title"]
            ).first()
            if existing_session:
                # Ensure speaker is linked
                existing_link = db.query(SessionSpeaker).filter(
                    SessionSpeaker.session_id == existing_session.id,
                    SessionSpeaker.user_id == speaker.id,
                ).first()
                if not existing_link:
                    db.add(SessionSpeaker(session_id=existing_session.id, user_id=speaker.id))
                continue

            # Create session with offset times
            start_time = session_base_date + timedelta(hours=i * 2)
            duration = session_data.get("duration_minutes", 60)
            end_time = start_time + timedelta(minutes=duration)

            new_session = Session(
                title=session_data["title"],
                description=session_data.get("description"),
                start_time=start_time,
                end_time=end_time,
                type=session_data.get("type", "talk"),
                venue_id=venue.id if venue else None,
            )
            db.add(new_session)
            db.flush()

            # Link speaker to session
            db.add(SessionSpeaker(session_id=new_session.id, user_id=speaker.id))
            sessions_created += 1

        db.commit()
        print(f"  Created {sessions_created} sessions for speakers")

        # ---------------------------
        # SCHEDULING DATA
        # ---------------------------
        print("\nSeeding scheduling data for matching users...")

        # Get matching users by email
        matching_emails = [TEST_USER["email"]] + [u["email"] for u in DUMMY_USERS]
        matching_users = db.execute(
            select(User).where(User.email.in_(matching_emails))
        ).scalars().all()

        if len(matching_users) < 2:
            print("Not enough matching users for scheduling data.")
        else:
            # Get a meeting location (room)
            location = db.execute(
                select(MapFeature).where(MapFeature.feature_type == "room").limit(1)
            ).scalar_one_or_none()

            # Base date for meetings (future date)
            base_date = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
            meetings_created = 0

            # Create meeting: testmatch -> alice (pending)
            test_user = next((u for u in matching_users if u.email == TEST_USER["email"]), None)
            alice = next((u for u in matching_users if u.email == "alice@test.com"), None)
            bob = next((u for u in matching_users if u.email == "bob@test.com"), None)
            charlie = next((u for u in matching_users if u.email == "charlie@test.com"), None)
            diana = next((u for u in matching_users if u.email == "diana@test.com"), None)

            if test_user and alice:
                existing = db.execute(
                    select(Meeting).where(
                        Meeting.requester_id == test_user.id,
                        Meeting.recipient_id == alice.id,
                    )
                ).scalar_one_or_none()
                if not existing:
                    m = Meeting(
                        requester_id=test_user.id,
                        recipient_id=alice.id,
                        proposed_start=base_date,
                        proposed_end=base_date + timedelta(minutes=30),
                        status=MeetingStatus.pending,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                        map_feature_id=location.id if location else None,
                        message="Let's discuss AI & ML trends!",
                    )
                    db.add(m)
                    meetings_created += 1

            # Create meeting: bob -> testmatch (pending - incoming request)
            if bob and test_user:
                existing = db.execute(
                    select(Meeting).where(
                        Meeting.requester_id == bob.id,
                        Meeting.recipient_id == test_user.id,
                    )
                ).scalar_one_or_none()
                if not existing:
                    m = Meeting(
                        requester_id=bob.id,
                        recipient_id=test_user.id,
                        proposed_start=base_date + timedelta(hours=2),
                        proposed_end=base_date + timedelta(hours=2, minutes=30),
                        status=MeetingStatus.pending,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                        map_feature_id=location.id if location else None,
                        message="Want to chat about Cloud Computing?",
                    )
                    db.add(m)
                    meetings_created += 1

            # Create meeting: alice -> diana (confirmed)
            if alice and diana:
                existing = db.execute(
                    select(Meeting).where(
                        Meeting.requester_id == alice.id,
                        Meeting.recipient_id == diana.id,
                    )
                ).scalar_one_or_none()
                if not existing:
                    m = Meeting(
                        requester_id=alice.id,
                        recipient_id=diana.id,
                        proposed_start=base_date + timedelta(hours=4),
                        proposed_end=base_date + timedelta(hours=4, minutes=30),
                        status=MeetingStatus.confirmed,
                        expires_at=None,
                        map_feature_id=location.id if location else None,
                        message="Robotics collaboration discussion",
                    )
                    db.add(m)
                    meetings_created += 1

            # Create meeting: charlie -> bob (declined - for history)
            if charlie and bob:
                existing = db.execute(
                    select(Meeting).where(
                        Meeting.requester_id == charlie.id,
                        Meeting.recipient_id == bob.id,
                    )
                ).scalar_one_or_none()
                if not existing:
                    m = Meeting(
                        requester_id=charlie.id,
                        recipient_id=bob.id,
                        proposed_start=base_date + timedelta(days=1),
                        proposed_end=base_date + timedelta(days=1, minutes=30),
                        status=MeetingStatus.declined,
                        expires_at=None,
                        map_feature_id=location.id if location else None,
                        message="Gaming meetup?",
                    )
                    db.add(m)
                    meetings_created += 1

            db.commit()
            print(f"Created {meetings_created} meetings for matching users")

            # Add sessions to agendas for conflict testing
            sessions = db.execute(
                select(Session).order_by(Session.start_time).limit(4)
            ).scalars().all()

            if sessions and test_user:
                agenda_added = 0
                for session in sessions[:2]:
                    existing = db.execute(
                        select(UserAgenda).where(
                            UserAgenda.user_id == test_user.id,
                            UserAgenda.session_id == session.id,
                        )
                    ).scalar_one_or_none()
                    if not existing:
                        db.add(UserAgenda(user_id=test_user.id, session_id=session.id))
                        agenda_added += 1
                db.commit()
                print(f"Added {agenda_added} sessions to test user's agenda")
            else:
                print("No sessions found. Skipping agenda seeding.")

        print(f"\nTest scheduling endpoints with:")
        print(f"   Email: {TEST_USER['email']}")
        print(f"   Password: {TEST_USER['password']}")

    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
