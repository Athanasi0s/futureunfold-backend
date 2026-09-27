"""Seed mock friend location sharing for testing Phase 1 friend tracking.

Creates group memberships with location sharing enabled and LocationShare
entries with coordinates scattered around the festival area.

Run with: python -m app.seed.seed_friend_locations
Requires: seed_users, seed_groups to have run first.
"""
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from app.db.session import SessionLocal
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.location_share import LocationShare


# Venue coordinates from seed_dummy_map — scatter friends very close to buildings
VENUE_CENTERS = [
    (37.9708, 23.7261),  # Acropolis area
    (37.9708, 23.7244),  # Odeon Herodes
    (37.9760, 23.7430),  # Athens Conservatoire
    (37.9720, 23.7428),  # National Gallery
    (37.9756, 23.7330),  # Maria Callas Museum
    (37.9720, 23.7309),  # Cine Paris
    (37.9830, 23.7325),  # French Institute
]
SPREAD = 0.00004  # ~4m around each venue — essentially at the building

# Counter to cycle through venues so each user gets a different one
_venue_idx = 0


def random_outdoor_point() -> tuple[float, float]:
    """Generate a random point very close to the next venue in rotation."""
    global _venue_idx
    center = VENUE_CENTERS[_venue_idx % len(VENUE_CENTERS)]
    _venue_idx += 1
    lat = center[0] + random.uniform(-SPREAD, SPREAD)
    lng = center[1] + random.uniform(-SPREAD, SPREAD)
    return (lat, lng)


def main():
    db: SASession = SessionLocal()
    try:
        users = db.execute(select(User)).scalars().all()
        groups = db.execute(
            select(Group).where(Group.group_type == "topic")
        ).scalars().all()

        if len(users) < 4:
            print("Need at least 4 users. Run seed_users and seed_matching_users first.")
            return
        if len(groups) < 3:
            print("Need at least 3 topic groups. Run seed_groups first.")
            return

        # Pick 3 groups for friend tracking demo
        demo_groups = groups[:3]
        # Pick users to distribute across groups (skip first user — that's likely "you")
        demo_users = users[1:min(len(users), 13)]  # up to 12 mock friends

        created_members = 0
        created_shares = 0

        for gi, group in enumerate(demo_groups):
            # Assign 3-5 users per group (overlapping is fine)
            start = gi * 3
            group_users = demo_users[start:start + 4]
            if not group_users:
                group_users = demo_users[:3]  # fallback

            for user in group_users:
                # Ensure GroupMember exists with sharing_location=True
                existing = db.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == group.id,
                        GroupMember.user_id == user.id,
                    )
                ).scalar_one_or_none()

                if existing:
                    if not existing.sharing_location:
                        existing.sharing_location = True
                else:
                    db.add(GroupMember(
                        group_id=group.id,
                        user_id=user.id,
                        role="member",
                        sharing_location=True,
                    ))
                    created_members += 1

                # Ensure LocationShare exists for this user+group
                existing_share = db.execute(
                    select(LocationShare).where(
                        LocationShare.user_id == user.id,
                        LocationShare.group_id == group.id,
                    )
                ).scalar_one_or_none()

                lat, lng = random_outdoor_point()
                if existing_share:
                    existing_share.latitude = lat
                    existing_share.longitude = lng
                    existing_share.updated_at = datetime.now(timezone.utc) + timedelta(days=30)
                else:
                    db.add(LocationShare(
                        user_id=user.id,
                        group_id=group.id,
                        latitude=lat,
                        longitude=lng,
                        updated_at=datetime.now(timezone.utc) + timedelta(days=30),
                    ))
                    created_shares += 1

            print(f"  Group '{group.title}': {len(group_users)} users sharing location")

        db.commit()
        print(f"\n✅ Seed friend locations complete.")
        print(f"   {created_members} new group memberships, {created_shares} new location shares")
        print(f"   Groups: {', '.join(g.title for g in demo_groups)}")
        print(f"\n   To test: open map, tap friends toggle, select these groups.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
