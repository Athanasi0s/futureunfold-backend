"""
Seed program sessions into the database.
Requires venues and speaker users to exist first.
Run with: python -m app.seed.seed_sessions
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.session import SessionLocal
from app.models.user import User
from app.core.enums import UserRole
from app.models.venue import Venue
from app.models.speaker import Speaker
from app.models.session import Session
from app.models.session_speaker import SessionSpeaker
from app.models.interest import Interest
from app.models.session_interest import SessionInterest

# Mapping from topic tags to interest names
TOPIC_TAG_TO_INTEREST: dict[str, str] = {
    # AI-related
    "ai": "AI & Machine Learning",
    "machine learning": "AI & Machine Learning",
    "deep learning": "AI & Machine Learning",
    "ethics": "AI & Machine Learning",
    # Blockchain
    "blockchain": "Blockchain",
    "web3": "Blockchain",
    # Climate/Green
    "climate tech": "Green Tech",
    "sustainability": "Green Tech",
    "green tech": "Green Tech",
    # Security
    "cybersecurity": "Cybersecurity",
    # Quantum
    "quantum computing": "Quantum Computing",
    # Cloud
    "cloud": "Cloud Computing",
    "architecture": "Cloud Computing",
    # DevOps
    "devops": "DevOps",
    # Data
    "data science": "Data Science",
    "visualization": "Data Science",
    "analytics": "Data Science",
    # Community
    "community": "Networking",
    "networking": "Networking",
}


def _link_session_interests(db, session: Session) -> int:
    """
    Link a session to interests based on its topic_tags.
    Returns count of new links created.
    """
    if not session.topic_tags:
        return 0

    linked = 0
    linked_interest_ids: set[int] = set()

    for tag in session.topic_tags:
        tag_lower = tag.lower()
        interest_name = TOPIC_TAG_TO_INTEREST.get(tag_lower)
        if not interest_name:
            continue

        interest = db.execute(
            select(Interest).where(Interest.name == interest_name)
        ).scalar_one_or_none()
        if not interest:
            continue

        # Skip if already linked (avoid duplicates from multiple tags mapping to same interest)
        if interest.id in linked_interest_ids:
            continue

        # Check if link already exists in DB
        existing_link = db.execute(
            select(SessionInterest).where(
                SessionInterest.session_id == session.id,
                SessionInterest.interest_id == interest.id,
            )
        ).scalar_one_or_none()

        if not existing_link:
            db.add(SessionInterest(session_id=session.id, interest_id=interest.id))
            linked += 1
            linked_interest_ids.add(interest.id)

    return linked


def seed_sessions():
    """Seed program sessions (idempotent - checks by title)."""
    db = SessionLocal()
    
    try:
        print("🌱 Seeding program sessions...")
        
        # ---------------------------
        # 1. CHECK PREREQUISITES
        # ---------------------------
        venues = db.execute(select(Venue).order_by(Venue.id)).scalars().all()
        if len(venues) == 0:
            print("❌ No venues found. Please run seed_dummy_map first.")
            return
        print(f"✅ Found {len(venues)} existing venues")
        
        # Get all speakers with their user info
        speakers = db.execute(
            select(Speaker).options(joinedload(Speaker.user))
        ).scalars().all()
        
        if len(speakers) == 0:
            print("❌ No speakers found. Please run seed_users first.")
            return
        print(f"✅ Found {len(speakers)} existing speakers")
        
        # Build email-to-speaker mapping for robust lookups
        email_to_speaker = {
            speaker.user.email.lower(): speaker
            for speaker in speakers
            if speaker.user
        }

        # Get an admin user for created_by, or fall back to first speaker's user
        admin_user = db.execute(
            select(User).where(User.role == UserRole.admin)
        ).scalars().first()

        default_creator_id = None
        if admin_user:
            default_creator_id = admin_user.id
            print(f"✅ Using admin user '{admin_user.email}' as default session creator")
        elif speakers and speakers[0].user:
            default_creator_id = speakers[0].user.id
            print(f"✅ Using speaker user '{speakers[0].user.email}' as default session creator")
        
        # ---------------------------
        # 2. DEFINE SESSIONS
        # ---------------------------
        base_date = datetime(2026, 5, 20, tzinfo=timezone.utc)
        
        sessions_data = [
            # Day 1 - May 20
            {
                "title": "Opening Keynote: The Future of AI in Greece",
                "description": "Explore how artificial intelligence is transforming industries across Greece and Europe. From healthcare to finance, discover the opportunities and challenges ahead.",
                "start_time": base_date.replace(hour=9, minute=0),
                "end_time": base_date.replace(hour=10, minute=0),
                "type": "keynote",
                "venue_id": venues[0].id if len(venues) > 0 else None,
                "topic_tags": ["AI", "Machine Learning", "Greece"],
                "slides_url": "https://example.com/slides/opening-keynote.pdf",
                "slides_unlocked": True,
                "image_url": "https://picsum.photos/seed/ai-keynote/800/450",
                "speaker_emails": ["maria.papadopoulou@speaker.com"],
            },
            {
                "title": "Workshop: Building Climate Tech Solutions",
                "description": "Hands-on workshop on developing sustainable technology solutions. Learn practical approaches to reducing carbon footprint through software.",
                "start_time": base_date.replace(hour=10, minute=30),
                "end_time": base_date.replace(hour=12, minute=30),
                "type": "workshop",
                "venue_id": venues[1].id if len(venues) > 1 else venues[0].id,
                "topic_tags": ["Climate Tech", "Sustainability", "Green Tech"],
                "slides_url": "https://example.com/slides/climate-workshop.pdf",
                "slides_unlocked": False,
                "image_url": "https://picsum.photos/seed/climate-tech/800/450",
                "speaker_emails": ["nikos.stavrou@speaker.com"],
            },
            {
                "title": "Panel: Cybersecurity in the Age of Quantum Computing",
                "description": "Industry experts discuss the implications of quantum computing on cybersecurity and how organizations should prepare.",
                "start_time": base_date.replace(hour=10, minute=30),
                "end_time": base_date.replace(hour=11, minute=30),
                "type": "panel",
                "venue_id": venues[2].id if len(venues) > 2 else venues[0].id,
                "topic_tags": ["Cybersecurity", "Quantum Computing", "Blockchain"],
                "image_url": "https://picsum.photos/seed/cybersecurity/800/450",
                "speaker_emails": ["elena.dimitriou@speaker.com", "alex.johnson@speaker.com"],
                "moderator_email": "elena.dimitriou@speaker.com",
            },
            {
                "title": "Lunch Break & Networking",
                "description": "Enjoy lunch and connect with fellow attendees, speakers, and sponsors.",
                "start_time": base_date.replace(hour=13, minute=0),
                "end_time": base_date.replace(hour=14, minute=0),
                "type": "break",
                "venue_id": venues[0].id,
                "topic_tags": ["Networking"],
                "speaker_emails": [],
            },
            {
                "title": "Data Visualization: Telling Stories with Data",
                "description": "Learn advanced techniques for creating compelling data visualizations that communicate insights effectively.",
                "start_time": base_date.replace(hour=14, minute=30),
                "end_time": base_date.replace(hour=16, minute=0),
                "type": "workshop",
                "venue_id": venues[1].id if len(venues) > 1 else venues[0].id,
                "topic_tags": ["Data Science", "Visualization", "Analytics"],
                "slides_url": "https://example.com/slides/dataviz.pdf",
                "slides_unlocked": False,
                "image_url": "https://picsum.photos/seed/dataviz/800/450",
                "speaker_emails": ["sofia.andronikou@speaker.com"],
            },
            {
                "title": "Closing Day 1: Building Tech Communities",
                "description": "Insights on fostering vibrant tech communities. Q&A with community leaders from across Greece.",
                "start_time": base_date.replace(hour=16, minute=30),
                "end_time": base_date.replace(hour=17, minute=30),
                "type": "keynote",
                "venue_id": venues[0].id,
                "topic_tags": ["Community", "Networking"],
                "image_url": "https://picsum.photos/seed/community/800/450",
                "speaker_emails": ["dimitris.kostas@speaker.com"],
            },
            # Day 2 - May 21
            {
                "title": "Morning Keynote: Cloud Native Architecture",
                "description": "Deep dive into modern cloud architecture patterns. Microservices, containers, and serverless computing explained.",
                "start_time": (base_date + timedelta(days=1)).replace(hour=9, minute=0),
                "end_time": (base_date + timedelta(days=1)).replace(hour=10, minute=0),
                "type": "keynote",
                "venue_id": venues[0].id,
                "topic_tags": ["Cloud", "Architecture", "DevOps"],
                "slides_url": "https://example.com/slides/cloud-native.pdf",
                "slides_unlocked": False,
                "image_url": "https://picsum.photos/seed/cloud-native/800/450",
                "speaker_emails": ["alex.johnson@speaker.com"],
            },
            {
                "title": "Panel: The Ethics of AI",
                "description": "Ethical considerations in AI development and deployment. Bias, privacy, and accountability.",
                "start_time": (base_date + timedelta(days=1)).replace(hour=10, minute=30),
                "end_time": (base_date + timedelta(days=1)).replace(hour=11, minute=30),
                "type": "panel",
                "venue_id": venues[2].id if len(venues) > 2 else venues[0].id,
                "topic_tags": ["AI", "Ethics", "Society"],
                "image_url": "https://picsum.photos/seed/ai-ethics/800/450",
                "speaker_emails": ["maria.papadopoulou@speaker.com", "sofia.andronikou@speaker.com"],
                "moderator_email": "maria.papadopoulou@speaker.com",
            },
            {
                "title": "Workshop: Advanced Machine Learning Techniques",
                "description": "Hands-on session covering transformer models, transfer learning, and model optimization.",
                "start_time": (base_date + timedelta(days=1)).replace(hour=14, minute=0),
                "end_time": (base_date + timedelta(days=1)).replace(hour=16, minute=30),
                "type": "workshop",
                "venue_id": venues[1].id if len(venues) > 1 else venues[0].id,
                "topic_tags": ["AI", "Machine Learning", "Deep Learning"],
                "slides_url": "https://example.com/slides/ml-advanced.pdf",
                "slides_unlocked": False,
                "image_url": "https://picsum.photos/seed/ml-advanced/800/450",
                "speaker_emails": ["maria.papadopoulou@speaker.com"],
            },
        ]
        
        # ---------------------------
        # 3. CREATE SESSIONS
        # ---------------------------
        created_sessions = 0
        skipped_sessions = 0
        interest_links = 0

        for sess_data in sessions_data:
            title = sess_data["title"]

            # Check if session already exists (by title)
            existing = db.execute(
                select(Session).where(Session.title == title)
            ).scalar_one_or_none()

            if existing:
                skipped_sessions += 1
                # Still link interests for existing sessions (idempotent)
                interest_links += _link_session_interests(db, existing)
                print(f"  ⏭️  Skipped existing session: {title}")
                continue

            # Extract custom fields
            speaker_emails = sess_data.pop("speaker_emails", [])
            moderator_email = sess_data.pop("moderator_email", None)

            # Resolve speaker IDs from emails
            speaker_ids = []
            for email in speaker_emails:
                speaker = email_to_speaker.get(email.lower())
                if speaker:
                    speaker_ids.append(speaker.id)
                else:
                    print(f"  ⚠️  Warning: Speaker not found for email {email}")

            moderator_id = None
            if moderator_email:
                moderator = email_to_speaker.get(moderator_email.lower())
                if moderator:
                    moderator_id = moderator.id

            # Create session with created_by
            session = Session(**sess_data, created_by=default_creator_id)
            db.add(session)
            db.commit()
            db.refresh(session)

            # Link speakers
            for speaker_id in speaker_ids:
                is_mod = (speaker_id == moderator_id)
                link = SessionSpeaker(
                    session_id=session.id,
                    user_id=speaker_id,
                    is_moderator=is_mod,
                )
                db.add(link)

            # Link interests based on topic_tags
            interest_links += _link_session_interests(db, session)

            db.commit()
            created_sessions += 1
            print(f"  ✅ Created session: {title}")

        db.commit()
        print(f"\n✅ Session seeding complete!")
        print(f"   - Created {created_sessions} new sessions")
        print(f"   - Skipped {skipped_sessions} existing sessions")
        print(f"   - Created {interest_links} interest links")
        print("\n📌 Test the API:")
        print("   - GET http://127.0.0.1:8000/program")
        print("   - GET http://127.0.0.1:8000/program?day=2026-05-20")
        print("   - GET http://127.0.0.1:8000/program?search=AI")
        print("   - GET http://127.0.0.1:8000/speakers")
        
    except Exception as e:
        print(f"❌ Error seeding sessions: {e}")
        db.rollback()
        raise
    finally:
        db.close()


run = seed_sessions

if __name__ == "__main__":
    run()
