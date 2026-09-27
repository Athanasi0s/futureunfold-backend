"""
Seed DM conversations and messages between existing test users.
Run with: python -m app.seed.seed_messages

Prerequisites: Run seed_matching_users first (creates alice, bob, charlie, diana, testmatch).
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message


def _sorted_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _get_or_create_conversation(db, user1_id: int, user2_id: int) -> Conversation:
    a, b = _sorted_pair(user1_id, user2_id)
    convo = db.query(Conversation).filter(
        Conversation.user_a_id == a, Conversation.user_b_id == b
    ).first()
    if convo:
        return convo
    convo = Conversation(user_a_id=a, user_b_id=b)
    db.add(convo)
    db.flush()
    return convo


# Conversation threads: (sender_email, recipient_email, messages[])
# Each message is (sender_email, text, minutes_offset)
CONVERSATIONS = [
    {
        "between": ("testmatch@test.com", "alice@test.com"),
        "messages": [
            ("testmatch@test.com", "Hey Alice! I saw your talk on Machine Learning, it was great!", 0),
            ("alice@test.com", "Thanks! Glad you enjoyed it. Are you working on something ML-related?", 2),
            ("testmatch@test.com", "Yes, I'm exploring computer vision for my startup. Would love to pick your brain.", 5),
            ("alice@test.com", "Of course! Let's grab coffee during the break. I'll be near the main stage.", 7),
            ("testmatch@test.com", "Perfect, see you there!", 8),
        ],
    },
    {
        "between": ("testmatch@test.com", "bob@test.com"),
        "messages": [
            ("bob@test.com", "Hi! We're in the same Cloud Computing group. What are you working on?", 0),
            ("testmatch@test.com", "Hey Bob! Building a SaaS platform. How about you?", 15),
            ("bob@test.com", "FinTech — decentralized lending. We should compare notes on cloud infra.", 18),
            ("testmatch@test.com", "Definitely. Are you using AWS or GCP?", 20),
            ("bob@test.com", "GCP mainly, but evaluating multi-cloud. You?", 22),
            ("testmatch@test.com", "AWS so far, but open to switching. Let's chat more at the networking event tonight.", 25),
        ],
    },
    {
        "between": ("testmatch@test.com", "diana@test.com"),
        "messages": [
            ("testmatch@test.com", "Hi Diana, your quantum computing keynote blew my mind!", 0),
            ("diana@test.com", "Thank you! It's a fascinating field. What caught your attention most?", 10),
            ("testmatch@test.com", "The part about quantum ML — combining quantum computing with AI.", 12),
        ],
    },
    {
        "between": ("alice@test.com", "diana@test.com"),
        "messages": [
            ("alice@test.com", "Diana! Long time no see. How's the quantum lab going?", 0),
            ("diana@test.com", "Alice! Great to see you here. We just got new funding for the robotics division.", 3),
            ("alice@test.com", "That's amazing! We should collaborate on the AI-robotics intersection.", 5),
            ("diana@test.com", "Absolutely. Let me send you our latest paper after the festival.", 8),
            ("alice@test.com", "Looking forward to it!", 9),
        ],
    },
    {
        "between": ("bob@test.com", "charlie@test.com"),
        "messages": [
            ("charlie@test.com", "Hey Bob, do you think blockchain could work for in-game economies?", 0),
            ("bob@test.com", "100%! NFTs for game assets are already a thing. What kind of game?", 5),
            ("charlie@test.com", "A VR multiplayer RPG. Players should be able to trade items freely.", 8),
            ("bob@test.com", "Sounds cool. I can help with the smart contract side if you want.", 10),
        ],
    },
]


def seed_messages():
    db = SessionLocal()
    try:
        print("Seeding DM conversations and messages...")

        # Load users by email
        emails = set()
        for conv in CONVERSATIONS:
            emails.add(conv["between"][0])
            emails.add(conv["between"][1])

        users = db.execute(
            select(User).where(User.email.in_(emails))
        ).scalars().all()
        user_map = {u.email: u for u in users}

        missing = emails - set(user_map.keys())
        if missing:
            print(f"  Missing users: {missing}")
            print("  Run seed_matching_users first: python -m app.seed.seed_matching_users")
            return

        # Count total messages to spread them evenly over the last 24 hours
        total_messages = sum(len(c["messages"]) for c in CONVERSATIONS)
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=1)
        # Gap between each message so the last one lands at ~now
        gap = timedelta(days=1) / total_messages

        conversations_created = 0
        messages_created = 0
        global_msg_index = 0

        for conv_data in CONVERSATIONS:
            email_a, email_b = conv_data["between"]
            user_a = user_map[email_a]
            user_b = user_map[email_b]

            convo = _get_or_create_conversation(db, user_a.id, user_b.id)

            # Check if messages already exist in this conversation
            existing_count = db.query(Message).filter(
                Message.conversation_id == convo.id
            ).count()
            if existing_count > 0:
                print(f"  Skipping {email_a} <-> {email_b} (already has {existing_count} messages)")
                global_msg_index += len(conv_data["messages"])
                continue

            conversations_created += 1

            for sender_email, text, _minutes_offset in conv_data["messages"]:
                sender = user_map[sender_email]
                recipient = user_map[email_b if sender_email == email_a else email_a]

                msg = Message(
                    conversation_id=convo.id,
                    sender_id=sender.id,
                    recipient_id=recipient.id,
                    text=text,
                    created_at=start_time + (gap * global_msg_index),
                )
                db.add(msg)
                messages_created += 1
                global_msg_index += 1

        db.commit()

        print(f"\nSeeding complete!")
        print(f"  Created {conversations_created} conversations")
        print(f"  Created {messages_created} messages")
        print(f"\nTest DM with these credentials:")
        print(f"  Email: testmatch@test.com")
        print(f"  Password: test1234")
        print(f"\n  This user has conversations with:")
        print(f"    - alice@test.com (5 messages)")
        print(f"    - bob@test.com (6 messages)")
        print(f"    - diana@test.com (3 messages)")

    except Exception as e:
        print(f"Error seeding messages: {e}")
        db.rollback()
        raise
    finally:
        db.close()


run = seed_messages

if __name__ == "__main__":
    run()
