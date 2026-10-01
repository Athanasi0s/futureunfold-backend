import logging
import os
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import EVENT_NAME, UPLOAD_DIR
from app.scheduler import create_scheduler, register_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start the background scheduler on startup, shut it down on teardown."""
    scheduler = create_scheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info("APScheduler started with %d jobs", len(scheduler.get_jobs()))
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down")


app = FastAPI(title=f"{EVENT_NAME} API", version="0.1.0", lifespan=lifespan)

# Για αρχή αφήνουμε CORS ανοιχτό, ώστε να μπορεί να καλεί το API το κινητό και το kiosk.
# Σε production θα βάλουμε συγκεκριμένα domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount StaticFiles for uploaded content BEFORE registering API routes.
# FastAPI matches in registration order; StaticFiles only serves files that exist on disk,
# so API routes are not shadowed.
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(api_router)

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/googlea75b39a9a0921f8d.html", response_class=HTMLResponse)
def google_site_verification():
    return "google-site-verification: googlea75b39a9a0921f8d.html"


_PAGE_STYLE = """body{font-family:system-ui,-apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#333;line-height:1.6}
h1{font-size:1.8rem;margin-bottom:4px}h2{font-size:1.2rem;margin-top:28px}
a{color:#4f46e5}footer{margin-top:40px;padding-top:16px;border-top:1px solid #ddd;font-size:0.85rem;color:#666}"""


@app.get("/", response_class=HTMLResponse)
def home_page():
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{EVENT_NAME}</title>
<style>{_PAGE_STYLE}</style>
</head><body>
<h1>{EVENT_NAME}</h1>
<p><strong>The official mobile app for the {EVENT_NAME} experience.</strong></p>

<h2>About</h2>
<p>{EVENT_NAME} is a cross-platform mobile application that helps attendees, speakers, and exhibitors
get the most out of the event. Features include:</p>
<ul>
<li>Personalised program schedule and agenda management</li>
<li>Networking and attendee matching based on shared interests</li>
<li>Meeting scheduling with availability and conflict detection</li>
<li>Interactive venue maps with indoor navigation</li>
<li>Direct messaging and group chat</li>
<li>Live polls, Q&amp;A sessions, and audience engagement</li>
<li>Points, rewards, leaderboard, and digital certificates</li>
<li>QR code check-ins and digital attendee badges</li>
<li>Google Calendar integration for meeting sync</li>
</ul>

<h2>Contact</h2>
<p>For questions or support, email <a href="mailto:festivity365@gmail.com">festivity365@gmail.com</a>.</p>

<footer>
<a href="/privacy">Privacy Policy</a> &middot; <a href="/terms">Terms of Service</a>
<br>&copy; 2026 {EVENT_NAME}
</footer>
</body></html>"""


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy — {EVENT_NAME}</title>
<style>{_PAGE_STYLE}</style>
</head><body>
<h1>Privacy Policy</h1>
<p><strong>{EVENT_NAME}</strong></p>
<p>This privacy policy is a placeholder and will be updated with full details before public release.</p>
<p>We collect only the information necessary to provide event services: your name, email, event preferences,
and calendar availability (when you opt in to Google Calendar integration). We do not sell your data to third parties.</p>
<p>If you have questions, contact us at <a href="mailto:festivity365@gmail.com">festivity365@gmail.com</a>.</p>
<p><em>Last updated: 10/2026</em></p>
<footer><a href="/">Home</a> &middot; <a href="/terms">Terms of Service</a></footer>
</body></html>"""


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Terms of Service — {EVENT_NAME}</title>
<style>{_PAGE_STYLE}</style>
</head><body>
<h1>Terms of Service</h1>
<p><strong>{EVENT_NAME}</strong></p>
<p>These terms of service are a placeholder and will be updated with full details before public release.</p>
<p>By using this app you agree to use it for its intended purpose of event participation. Misuse, harassment,
or abuse of other users may result in account suspension.</p>
<p>If you have questions, contact us at <a href="mailto:festivity365@gmail.com">festivity365@gmail.com</a>.</p>
<p><em>Last updated: 10/2026</em></p>
<footer><a href="/">Home</a> &middot; <a href="/privacy">Privacy Policy</a></footer>
</body></html>"""
