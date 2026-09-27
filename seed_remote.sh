#!/bin/bash
DB="postgresql+psycopg2://festapp_api_panathenea:xmBg1hpLO0RUZGZ@localhost:15432/festapp_api_panathenea?sslmode=disable"

export DATABASE_URL="$DB"

echo "Seeding dummy map..."
python -m app.seed.seed_dummy_map

echo "Seeding users..."
python -m app.seed.seed_users

echo "Seeding interests..."
python -m app.seed.seed_interests

echo "Seeding groups..."
python -m app.seed.seed_groups

echo "Seeding sessions..."
python -m app.seed.seed_sessions

echo "Seeding goals..."
python -m app.seed.seed_goals

echo "Seeding matching users..."
python -m app.seed.seed_matching_users

echo "Seeding scheduling..."
python -m app.seed.seed_scheduling

echo "All done!"
