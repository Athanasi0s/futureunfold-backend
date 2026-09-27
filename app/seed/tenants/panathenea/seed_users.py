"""
Seed speaker users into the database.
Run with: python -m app.seed.seed_users
"""

from datetime import datetime, timezone
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.core.enums import UserRole
from app.models.speaker import Speaker


def seed_users():
    """Seed speaker users with their Speaker records (idempotent)."""
    db = SessionLocal()
    
    try:
        print("🌱 Seeding speaker users...")
        
        # Speaker data with emails as keys for idempotency
        speakers_data = [
            {
                "email": "a@a.a",
                "full_name": "a",
                "company": "A Labs Coorporation",
                "bio": "A developer",
                "avatar_url": "https://i.pravatar.cc/300?img=a",
                "linkedin_url": "https://linkedin.com/in/a",
            },
            {
                "email": "maria.papadopoulou@speaker.com",
                "full_name": "Dr. Maria Papadopoulou",
                "company": "Athens Tech Institute",
                "bio": "Leading researcher in machine learning with 15+ years experience. Published 40+ papers on neural networks and computer vision.",
                "avatar_url": "https://i.pravatar.cc/300?img=1",
                "linkedin_url": "https://linkedin.com/in/maria-papadopoulou",
            },
            {
                "email": "maria.papadopoulou@speaker.com",
                "full_name": "Dr. Maria Papadopoulou",
                "company": "Athens Tech Institute",
                "bio": "Leading researcher in machine learning with 15+ years experience. Published 40+ papers on neural networks and computer vision.",
                "avatar_url": "https://i.pravatar.cc/300?img=1",
                "linkedin_url": "https://linkedin.com/in/maria-papadopoulou",
            },
            {
                "email": "nikos.stavrou@speaker.com",
                "full_name": "Nikos Stavrou",
                "company": "GreenTech Solutions",
                "bio": "Serial entrepreneur focused on climate tech. Former engineer at Google. Founded 3 successful startups.",
                "avatar_url": "https://i.pravatar.cc/300?img=2",
                "linkedin_url": "https://linkedin.com/in/nikos-stavrou",
            },
            {
                "email": "elena.dimitriou@speaker.com",
                "full_name": "Elena Dimitriou",
                "company": "CyberSafe EU",
                "bio": "Expert in cybersecurity and blockchain technologies. Advises governments on digital infrastructure.",
                "avatar_url": "https://i.pravatar.cc/300?img=3",
                "linkedin_url": "https://linkedin.com/in/elena-dimitriou",
            },
            {
                "email": "alex.johnson@speaker.com",
                "full_name": "Alex Johnson",
                "company": "Microsoft",
                "bio": "Leading product innovation in cloud computing. Former startup founder acquired by Microsoft in 2020.",
                "avatar_url": "https://i.pravatar.cc/300?img=4",
                "linkedin_url": "https://linkedin.com/in/alex-johnson",
            },
            {
                "email": "sofia.andronikou@speaker.com",
                "full_name": "Sofia Andronikou",
                "company": "DataViz Labs",
                "bio": "Specializes in data visualization and analytics. TEDx speaker and author of 'Data Stories'.",
                "avatar_url": "https://i.pravatar.cc/300?img=5",
                "linkedin_url": "https://linkedin.com/in/sofia-andronikou",
            },
            {
                "email": "dimitris.kostas@speaker.com",
                "full_name": "Dimitris Kostas",
                "company": "DevHub Greece",
                "bio": "Building tech communities across Greece. Organizer of Athens DevFest and Python Athens meetups.",
                "avatar_url": "https://i.pravatar.cc/300?img=6",
                "linkedin_url": "https://linkedin.com/in/dimitris-kostas",
            },
        ]
        
        # Pre-hashed password for demo (bcrypt hash of "speaker123")
        demo_password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5UpJRw6FS/2WK"
        
        created_users = 0
        created_speakers = 0
        skipped_users = 0
        
        for speaker_data in speakers_data:
            email = speaker_data["email"].lower()
            
            # Check if user already exists
            existing_user = db.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            
            if existing_user:
                user = existing_user
                skipped_users += 1
            else:
                # Create new user
                user = User(
                    email=email,
                    password_hash=demo_password_hash,
                    full_name=speaker_data["full_name"],
                    role=UserRole.speaker,
                    company=speaker_data.get("company"),
                    bio=speaker_data.get("bio"),
                    avatar_url=speaker_data.get("avatar_url"),
                    linkedin_url=speaker_data.get("linkedin_url"),
                    last_seen=datetime.now(timezone.utc),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                created_users += 1
                print(f"  ✅ Created user: {user.full_name} ({user.email})")
            
            # Ensure Speaker record exists
            existing_speaker = db.execute(
                select(Speaker).where(Speaker.user_id == user.id)
            ).scalar_one_or_none()
            
            if not existing_speaker:
                speaker = Speaker(user_id=user.id)
                db.add(speaker)
                db.commit()
                db.refresh(speaker)
                created_speakers += 1
                print(f"  ✅ Created Speaker record for: {user.full_name}")
        
        print(f"\n✅ User seeding complete!")
        print(f"   - Created {created_users} new users")
        print(f"   - Skipped {skipped_users} existing users")
        print(f"   - Created {created_speakers} new Speaker records")
        
    except Exception as e:
        print(f"❌ Error seeding users: {e}")
        db.rollback()
        raise
    finally:
        db.close()


run = seed_users

if __name__ == "__main__":
    run()
