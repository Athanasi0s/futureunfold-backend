# app/seed/seed_interests.py
# Seed διαθέσιμα interests στη βάση.

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.interest import Interest

INTERESTS = [
    "AI & Machine Learning",
    "Blockchain",
    "Cloud Computing",
    "Cybersecurity",
    "Data Science",
    "DevOps",
    "FinTech",
    "Gaming",
    "Green Tech",
    "IoT",
    "Mobile Development",
    "Networking",
    "Open Source",
    "Quantum Computing",
    "Robotics",
    "Smart Cities",
    "Startups",
    "UX/UI Design",
    "VR/AR",
    "Web Development",
]


def main():
    db: Session = SessionLocal()
    try:
        created = 0
        for name in INTERESTS:
            exists = db.query(Interest).filter(Interest.name == name).first()
            if not exists:
                db.add(Interest(name=name))
                created += 1

        db.commit()
        print(f"Seed interests done. Created {created} interests.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
