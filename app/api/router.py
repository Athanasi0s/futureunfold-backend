from fastapi import APIRouter
from app.api.routes.venues import router as venues_router
from app.api.routes.auth import router as auth_router
from app.api.routes.groups import router as groups_router
from app.api.routes.group_messages import router as group_messages_router
from app.api.routes.dm import router as dm_router
from app.api.routes.program import router as program_router
from app.api.routes.interests import router as interests_router
from app.api.routes.matching import router as matching_router
from app.api.routes.scheduling import router as scheduling_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.users import router as users_router
from app.api.routes.polls import router as polls_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.exhibitors import router as exhibitors_router
from app.api.routes.qr import router as qr_router
from app.api.routes.rewards import router as rewards_router
from app.api.routes.session_chat import router as session_chat_router
from app.api.routes.exhibitor_chat import router as exhibitor_chat_router
from app.api.routes.location import router as location_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.density import router as density_router
from app.api.routes.google_calendar import router as google_calendar_router
from app.api.routes.ticketing import router as ticketing_router, webhook_router as ticketing_webhook_router
from app.api.routes.session_qa import router as session_qa_router
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_venues import router as admin_venues_router
from app.api.routes.admin_groups import router as admin_groups_router
from app.api.routes.admin_interests import router as admin_interests_router
from app.api.routes.admin_goals import router as admin_goals_router
from app.api.routes.admin_push import router as admin_push_router
from app.api.routes.user_actions import router as user_actions_router
from app.api.routes.config import router as config_router
from app.api.routes.upload import router as upload_router
from app.api.routes.wallet import router as wallet_router
from app.api.routes.first_phase_auth import router as first_phase_auth_router

api_router = APIRouter()

api_router.include_router(venues_router, prefix="", tags=["venues"])
api_router.include_router(auth_router, prefix="", tags=["auth"])
api_router.include_router(groups_router, prefix="", tags=["groups"])
api_router.include_router(group_messages_router, prefix="", tags=["group-messages"])
api_router.include_router(dm_router, prefix="", tags=["dm"])
api_router.include_router(program_router, prefix="", tags=["program"])
api_router.include_router(interests_router, prefix="", tags=["interests"])
api_router.include_router(matching_router, prefix="", tags=["matching"])
api_router.include_router(scheduling_router, prefix="", tags=["scheduling"])
api_router.include_router(onboarding_router, prefix="", tags=["onboarding"])
api_router.include_router(users_router, prefix="", tags=["users"])
api_router.include_router(polls_router, prefix="", tags=["polls"])
api_router.include_router(recommendations_router, prefix="", tags=["recommendations"])
api_router.include_router(exhibitors_router, prefix="", tags=["exhibitors"])
api_router.include_router(qr_router, prefix="", tags=["qr"])
api_router.include_router(rewards_router, prefix="", tags=["rewards"])
api_router.include_router(session_chat_router, prefix="", tags=["session-chat"])
api_router.include_router(exhibitor_chat_router, prefix="", tags=["exhibitor-chat"])
api_router.include_router(location_router, prefix="", tags=["location"])
api_router.include_router(notifications_router, prefix="", tags=["notifications"])
api_router.include_router(density_router, prefix="", tags=["density"])
api_router.include_router(google_calendar_router, prefix="", tags=["google-calendar"])
api_router.include_router(ticketing_router, prefix="", tags=["ticketing"])
api_router.include_router(ticketing_webhook_router, prefix="", tags=["ticketing-webhooks"])
api_router.include_router(session_qa_router, prefix="", tags=["session-qa"])
api_router.include_router(admin_router, prefix="", tags=["admin"])
api_router.include_router(admin_venues_router, prefix="", tags=["admin-venues"])
api_router.include_router(admin_groups_router, prefix="", tags=["admin-groups"])
api_router.include_router(admin_interests_router, prefix="", tags=["admin-interests"])
api_router.include_router(admin_goals_router, prefix="", tags=["admin-goals"])
api_router.include_router(admin_push_router, prefix="", tags=["admin-push"])
api_router.include_router(user_actions_router, prefix="", tags=["user-actions"])
api_router.include_router(config_router, prefix="", tags=["config"])
api_router.include_router(upload_router, prefix="", tags=["upload"])
api_router.include_router(wallet_router, prefix="", tags=["wallet"])
api_router.include_router(first_phase_auth_router, prefix="", tags=["first-phase-auth"])
