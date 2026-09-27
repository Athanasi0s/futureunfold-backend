"""
Seed 3 ticket packages. Run after stripe products/prices are created (Task 9).
Update stripe_price_id values to match your Stripe test price IDs.
Idempotent — uses ref_key as the upsert key.
"""
from app.db.session import SessionLocal
from app.models.ticket_package import TicketPackage

PACKAGES = [
    {
        "ref_key": "ticket_01",
        "name": "Standard Pass",
        "price_eur": "49.00",
        "description": "Full festival access for one day.",
        "features": ["One-day access", "Session attendance", "Wi-Fi access"],
        "stripe_price_id": "price_1T9kx0Ek3PYLI21jgrv4NJGT",
        "max_quantity": None,
        "is_active": True,
    },
    {
        "ref_key": "ticket_02",
        "name": "Full Festival Pass",
        "price_eur": "89.00",
        "description": "Access to all festival days and sessions.",
        "features": ["Multi-day access", "All sessions", "Wi-Fi access", "Networking events"],
        "stripe_price_id": "price_1T9kxZEk3PYLI21jMU9ZV9Cc",
        "max_quantity": 200,
        "is_active": True,
    },
    {
        "ref_key": "ticket_03",
        "name": "VIP Pass",
        "price_eur": "149.00",
        "description": "Premium access with reserved seating and lounge.",
        "features": ["All-access", "Reserved seating", "VIP lounge", "Speaker meet & greet", "Lunch included"],
        "stripe_price_id": "price_1T9ky1Ek3PYLI21jW4ZURcNa",
        "max_quantity": 50,
        "is_active": True,
    },
]


def main():
    db = SessionLocal()
    try:
        for data in PACKAGES:
            pkg = db.query(TicketPackage).filter(TicketPackage.ref_key == data["ref_key"]).first()
            if pkg:
                for k, v in data.items():
                    setattr(pkg, k, v)
            else:
                db.add(TicketPackage(**data))
        db.commit()
        print("Ticket packages seeded.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
