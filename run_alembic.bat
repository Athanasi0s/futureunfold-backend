@echo off
cd /d C:\Users\sarmatas\Desktop\festapp-backend
set DATABASE_URL=postgresql+psycopg2://panathenea:panathenea@localhost:5442/panathenea
.venv\Scripts\alembic.exe revision --autogenerate -m "add_outdoor_map_fields_to_venues" > C:\Users\sarmatas\Desktop\alembic_out.txt 2>&1
echo Exit code: %ERRORLEVEL% >> C:\Users\sarmatas\Desktop\alembic_out.txt
