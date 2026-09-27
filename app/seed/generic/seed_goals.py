# app/seed/seed_goals.py
# Seed goals for onboarding.

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.goal import Goal

GOALS = [
    {
        "name": "Find co-founders",
        "description": "Looking for partners to start a venture together",
        "display_order": 1,
    },
    {
        "name": "Get funding",
        "description": "Seeking investment for my startup",
        "display_order": 2,
    },
    {
        "name": "Find mentors",
        "description": "Looking for experienced advisors to guide me",
        "display_order": 3,
    },
    {
        "name": "Expand network",
        "description": "Building connections in the startup ecosystem",
        "display_order": 4,
    },
    {
        "name": "Learn new skills",
        "description": "Gaining knowledge and expertise",
        "display_order": 5,
    },
    {
        "name": "Find talent",
        "description": "Recruiting team members for my company",
        "display_order": 6,
    },
]


def main():
    db: Session = SessionLocal()
    try:
        created = 0
        for goal_data in GOALS:
            exists = db.query(Goal).filter(Goal.name == goal_data["name"]).first()
            if not exists:
                db.add(Goal(**goal_data))
                created += 1

        db.commit()
        print(f"Seed goals done. Created {created} goals.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
