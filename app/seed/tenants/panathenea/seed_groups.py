# app/seed/seed_groups.py
# Seed αρχικά groups στη βάση για να μην είναι άδεια η λίστα /groups.

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.venue import Venue
from app.models.group import Group
from app.models.interest import Interest
from app.models.group_interest import GroupInterest

TOPICS = [
    ("topic", "ai_deeptech", "AI & DeepTech"),
    ("topic", "blockchain_web3", "Blockchain / Web3"),
    ("topic", "climate_tech", "Climate Tech"),
    ("topic", "cloud_cyber", "Cloud & Cybersecurity"),
    ("topic", "smart_city_mobility", "Smart City & Mobility"),
    ("topic", "women_in_tech", "Women in Tech"),
]

# Mapping from group ref_key to interest names
TOPIC_TO_INTERESTS: dict[str, list[str]] = {
    "ai_deeptech": ["AI & Machine Learning"],
    "blockchain_web3": ["Blockchain"],
    "climate_tech": ["Green Tech"],
    "cloud_cyber": ["Cloud Computing", "Cybersecurity"],
    "smart_city_mobility": ["Smart Cities", "IoT"],
}

def _link_group_interests(db: Session, group: Group, interest_names: list[str]) -> int:
    """Link a group to interests by name. Returns count of new links created."""
    linked = 0
    for interest_name in interest_names:
        interest = db.execute(
            select(Interest).where(Interest.name == interest_name)
        ).scalar_one_or_none()
        if not interest:
            print(f"  ⚠️  Interest not found: {interest_name}")
            continue

        # Check if link already exists
        existing_link = db.execute(
            select(GroupInterest).where(
                GroupInterest.group_id == group.id,
                GroupInterest.interest_id == interest.id,
            )
        ).scalar_one_or_none()

        if not existing_link:
            db.add(GroupInterest(group_id=group.id, interest_id=interest.id))
            linked += 1
    return linked


def main():
    db: Session = SessionLocal()
    try:
        created = 0
        interest_links = 0

        # 1) Ένα group ανά venue
        venues = db.query(Venue).all()
        for v in venues:
            exists = (
                db.query(Group)
                .filter(Group.group_type == "venue", Group.ref_key == v.key)
                .first()
            )
            if not exists:
                g = Group(
                    group_type="venue",
                    ref_key=v.key,
                    title=f"Venue: {v.name}",
                    description="",
                )
                db.add(g)
                created += 1

        # 2) Groups για Topics
        for group_type, ref_key, title in TOPICS:
            existing = (
                db.query(Group)
                .filter(Group.group_type == group_type, Group.ref_key == ref_key)
                .first()
            )
            if not existing:
                g = Group(
                    group_type=group_type,
                    ref_key=ref_key,
                    title=title,
                    description="",
                )
                db.add(g)
                db.flush()  # Get the ID
                created += 1
            else:
                g = existing

            # Link interests to group
            if ref_key in TOPIC_TO_INTERESTS:
                interest_links += _link_group_interests(db, g, TOPIC_TO_INTERESTS[ref_key])

        db.commit()
        print(f"✅ Seed groups ολοκληρώθηκε. Δημιουργήθηκαν {created} groups, {interest_links} interest links.")
    finally:
        db.close()

run = main

if __name__ == "__main__":
    run()

