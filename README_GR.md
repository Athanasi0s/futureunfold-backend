# Panathenea Backend

Backend API.

## Tech Stack

- Python 3.11
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker & Docker Compose

---

## Requirements

- Docker
- Docker Compose
- Git

---

## Setup (ΑΠΛΑ ΒΗΜΑΤΑ)

### 1. Clone repo

````bash
git clone <repo-url>
cd backend


=======================================
1. Open Powershell

2. Start database
docker compose up -d

3. Create virtual environment
python -m venv .venv

4. Activate venv (Windows)
.venv\Scripts\Activate.ps1

5. Install dependencies
pip install -r requirements.txt

6. Run migrations
alembic upgrade head

7. Start backend
uvicorn app.main:app --reload

8.API Docs

Open browser at:

http://127.0.0.1:8000/docs
=======================================

# Panathenea – Milestone 1


## Τι φτιάχνουμε σε αυτό το milestone
Σε αυτό το βήμα θα φτιάξουμε το “πίσω μέρος” της εφαρμογής (backend) και **τη βάση δεδομένων** ώστε:

1) Να σηκώνεται τοπικά (στον υπολογιστή) μια βάση PostgreSQL.
2) Να σηκώνεται τοπικά ένα API (FastAPI).
3) Να έχει μέσα **dummy venues** και **dummy floors** με **dummy GeoJSON** (booths/rooms) ώστε το κινητό να μπορεί να:
   - ζητάει `/venues` (pins για outdoor map)
   - ζητάει `/venues/{id}/floors` (λίστα ορόφων)
   - ζητάει `/venues/{id}/floors/{floor}/geojson` (σχήματα για indoor map)

> **Σημαντικό:** “dummy” σημαίνει “προσωρινά σχήματα” μόνο για να δουλέψει η λογική (tap, highlight, floors). Αργότερα τα αντικαθιστούμε με τα πραγματικά σχέδια χωρίς να αλλάξουμε τη λογική.


## Τι χρειάζεσαι να εγκαταστήσεις

### 1) Docker Desktop
Για να τρέχουμε τη βάση δεδομένων **χωρίς να τη στήσεις χειροκίνητα**.

### 2) Python 3.11
Για να τρέχει το backend.

### 3) Ένα πρόγραμμα τερματικού
- Windows: PowerShell ή Windows Terminal
- Mac: Terminal
- Linux: Terminal

> Αν έχεις **VS Code**, βοηθάει πολύ, αλλά δεν είναι υποχρεωτικό.

---

## Βήμα-βήμα: Πώς το τρέχεις

### Βήμα 0: Πήγαινε στον φάκελο `backend`
Άνοιξε τερματικό και πήγαινε στον φάκελο:

- Windows (παράδειγμα):
  - άνοιξε το φάκελο που κατέβασες το project
  - μετά `cd backend`

### Βήμα 1: Σήκωσε τη βάση δεδομένων
Μέσα στο `backend` τρέχεις:

```bash docker compose up -d
````

Αυτό θα ξεκινήσει τη βάση PostgreSQL.

### Βήμα 2: Φτιάξε αρχείο ρυθμίσεων `.env`

Στον ίδιο φάκελο (`backend`) κάνε αντιγραφή το `.env.example` σε `.env`.

- Windows PowerShell:

```powershell
copy .env.example .env
```

- Mac/Linux:

```bash
cp .env.example .env
```

### Βήμα 3: Εγκατάσταση “βιβλιοθηκών” Python

Στον φάκελο `backend`:

```bash
python -m venv .venv
```

Ενεργοποίηση:

- Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

- Mac/Linux:

```bash
source .venv/bin/activate
```

Μετά εγκατάσταση:

```bash
pip install -r requirements.txt
```

### Βήμα 4: Φτιάξε τους πίνακες στη βάση (migrations)

Τρέχεις:

```bash
alembic upgrade head
```

### Βήμα 5: Γέμισε τη βάση με dummy δεδομένα (seed)

Τρέχεις:

```bash
python -m app.seed.seed_dummy_map
```

Θα δεις μήνυμα: `Seed ολοκληρώθηκε επιτυχώς!

### Βήμα 6: Τρέξε το API

Τρέχεις:

```bash
uvicorn app.main:app --reload
# Expose to local network for expo go to connect
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 
```

### Βήμα 7: Έλεγχος ότι όλα δουλεύουν

Άνοιξε browser και πήγαινε:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/venues`

---

## Τι κερδίζουμε με αυτό το milestone

- Έχουμε **σταθερή βάση** για όλο το project.
- Δεν “χτίζουμε στα τυφλά” οθόνες: το κινητό θα παίρνει πραγματικά δεδομένα.
- Έχουμε ήδη έτοιμη δομή για **πολλούς ορόφους + outdoor**.

---

---

## ΝΕΟ: Groups & Προσωπικά Μηνύματα (DM) – βασικές δοκιμές

Σε αυτό το ενημερωμένο Milestone 1, προσθέσαμε:

- **Χρήστες** (για να μπορείς να κάνεις login)
- **Groups** (Join/Leave + λίστα “My Groups”)
- **Προσωπικά μηνύματα** (απλά μηνύματα, με:
  - **block/report**
  - όριο **50 μηνύματα/ημέρα** ανά χρήστη)

### Έτοιμοι δοκιμαστικοί χρήστες

Μετά το seed (`python -m app.seed.seed_dummy_map`) θα υπάρχουν:

- Alice: `alice@example.com` / `123456`
- Bob: `bob@example.com` / `123456`
- Exhibitor Demo: `exhibitor@example.com` / `123456`

### Login (για να πάρεις token)

1. Άνοιξε το Swagger (δοκιμαστικό UI του API):
   - `http://127.0.0.1:8000/docs`

2. Βρες το endpoint `POST /auth/login` και βάλε:
   - email: `alice@example.com`
   - password: `123456`

3. Θα πάρεις `access_token`.

4. Στο πάνω μέρος του Swagger πάτα **Authorize** και βάλε:
   - `Bearer <το_token_σου>`

Από εκεί και πέρα, τα “προσωπικά” endpoints θα δουλεύουν.

### Groups

- `GET /groups` → δείχνει όλα τα διαθέσιμα groups (για δοκιμή)
- `POST /groups/join` → κάνεις συμμετοχή (με `group_id` ή `ref_key`)
- `DELETE /groups/leave/{group_id}` → φεύγεις από ομάδα
- `GET /me/groups` → βλέπεις σε ποιες ομάδες είσαι

### Προσωπικά μηνύματα (DM)

- `POST /dm/send` → στέλνεις μήνυμα σε άλλον χρήστη (`to_user_id`)
- `GET /dm/inbox` → λίστα συνομιλιών
- `GET /dm/conversations/{id}/messages` → όλα τα μηνύματα μιας συνομιλίας
- `POST /dm/block/{user_id}` → κάνεις block
- `DELETE /dm/block/{user_id}` → βγάζεις block
- `POST /dm/report/{user_id}` → κάνεις report (με λόγο)
