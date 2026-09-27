from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.enums import OnboardingStatus, ExperienceLevel, DiscussionTopic
from app.models.user import User
from app.models.interest import Interest
from app.models.user_interest import UserInterest
from app.models.goal import Goal
from app.models.user_goal import UserGoal
from app.models.user_onboarding import UserOnboarding
from app.services.config_reader import get_config_value
from app.api.schemas import (
    InterestOut,
    GoalOut,
    ExperienceLevelOption,
    DiscussionTopicOption,
    OnboardingQuestionsOut,
    OnboardingDataOut,
    OnboardingUpdateIn,
)

router = APIRouter()

# Default experience level options
DEFAULT_EXPERIENCE_LEVEL_OPTIONS = [
    {"value": "beginner", "label": "Just starting out", "years": "0-1 years"},
    {"value": "early_stage", "label": "Early stage", "years": "1-3 years"},
    {"value": "experienced", "label": "Experienced", "years": "3-7 years"},
    {"value": "expert", "label": "Expert/Veteran", "years": "7+ years"},
]

# Default discussion topic options
DEFAULT_DISCUSSION_TOPIC_OPTIONS = [
    {"value": "fundraising", "label": "Fundraising strategies"},
    {"value": "product_market_fit", "label": "Product-market fit"},
    {"value": "scaling_teams", "label": "Scaling teams/team building"},
]

# Static metadata for experience levels (hardcoded fallback)
EXPERIENCE_LEVEL_OPTIONS = [
    ExperienceLevelOption(
        value=ExperienceLevel.beginner,
        label="Just starting out",
        years="0-1 years",
    ),
    ExperienceLevelOption(
        value=ExperienceLevel.early_stage,
        label="Early stage",
        years="1-3 years",
    ),
    ExperienceLevelOption(
        value=ExperienceLevel.experienced,
        label="Experienced",
        years="3-7 years",
    ),
    ExperienceLevelOption(
        value=ExperienceLevel.expert,
        label="Expert/Veteran",
        years="7+ years",
    ),
]

# Static metadata for discussion topics (hardcoded fallback)
DISCUSSION_TOPIC_OPTIONS = [
    DiscussionTopicOption(
        value=DiscussionTopic.fundraising,
        label="Fundraising strategies",
    ),
    DiscussionTopicOption(
        value=DiscussionTopic.product_market_fit,
        label="Product-market fit",
    ),
    DiscussionTopicOption(
        value=DiscussionTopic.scaling_teams,
        label="Scaling teams/team building",
    ),
]


def _get_experience_levels(db: Session) -> list[ExperienceLevelOption]:
    """Load experience levels from config, falling back to hardcoded defaults."""
    config_levels = get_config_value(db, "experience_levels", None)
    if config_levels and isinstance(config_levels, list):
        try:
            return [
                ExperienceLevelOption(
                    value=ExperienceLevel(item["value"]),
                    label=item["label"],
                    years=item.get("years", ""),
                )
                for item in config_levels
            ]
        except (KeyError, ValueError):
            pass
    return EXPERIENCE_LEVEL_OPTIONS


def _get_discussion_topics(db: Session) -> list[DiscussionTopicOption]:
    """Load discussion topics from config, falling back to hardcoded defaults."""
    config_topics = get_config_value(db, "discussion_topics", None)
    if config_topics and isinstance(config_topics, list):
        try:
            return [
                DiscussionTopicOption(
                    value=DiscussionTopic(item["value"]),
                    label=item["label"],
                )
                for item in config_topics
            ]
        except (KeyError, ValueError):
            pass
    return DISCUSSION_TOPIC_OPTIONS


@router.get("/onboarding/questions", response_model=OnboardingQuestionsOut)
def get_onboarding_questions(db: Session = Depends(get_db)):
    """Returns all available onboarding options (public endpoint)."""
    interests = db.query(Interest).order_by(Interest.name).all()
    goals = db.query(Goal).order_by(Goal.display_order, Goal.name).all()

    return OnboardingQuestionsOut(
        interests=[InterestOut(id=i.id, name=i.name) for i in interests],
        goals=[GoalOut(id=g.id, name=g.name, description=g.description) for g in goals],
        experience_levels=_get_experience_levels(db),
        discussion_topics=_get_discussion_topics(db),
    )


@router.get("/onboarding", response_model=OnboardingDataOut)
def get_user_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the current user's onboarding data."""
    # Get onboarding record
    onboarding = db.query(UserOnboarding).filter(
        UserOnboarding.user_id == current_user.id
    ).first()

    # Get user's interests
    interest_ids = [
        row[0] for row in db.query(UserInterest.interest_id)
        .filter(UserInterest.user_id == current_user.id)
        .all()
    ]

    # Get user's goals
    goal_ids = [
        row[0] for row in db.query(UserGoal.goal_id)
        .filter(UserGoal.user_id == current_user.id)
        .all()
    ]

    if onboarding:
        return OnboardingDataOut(
            status=onboarding.status,
            interest_ids=interest_ids,
            goal_ids=goal_ids,
            experience_level=onboarding.experience_level,
            discussion_topics=[
                DiscussionTopic(t) for t in (onboarding.discussion_topics or [])
            ],
            completed_at=onboarding.completed_at.isoformat() if onboarding.completed_at else None,
        )
    else:
        return OnboardingDataOut(
            status=OnboardingStatus.pending,
            interest_ids=interest_ids,
            goal_ids=goal_ids,
            experience_level=None,
            discussion_topics=[],
            completed_at=None,
        )


@router.put("/onboarding", response_model=OnboardingDataOut)
def update_user_onboarding(
    payload: OnboardingUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates all onboarding data for the current user."""
    # Validate interest IDs exist
    if payload.interest_ids:
        existing = db.query(Interest.id).filter(
            Interest.id.in_(payload.interest_ids)
        ).all()
        existing_ids = {row[0] for row in existing}
        invalid = set(payload.interest_ids) - existing_ids
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interest IDs: {sorted(invalid)}",
            )

    # Validate goal IDs exist
    if payload.goal_ids:
        existing = db.query(Goal.id).filter(
            Goal.id.in_(payload.goal_ids)
        ).all()
        existing_ids = {row[0] for row in existing}
        invalid = set(payload.goal_ids) - existing_ids
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid goal IDs: {sorted(invalid)}",
            )

    # Update interests
    db.query(UserInterest).filter(UserInterest.user_id == current_user.id).delete()
    for interest_id in payload.interest_ids:
        db.add(UserInterest(user_id=current_user.id, interest_id=interest_id))

    # Update goals
    db.query(UserGoal).filter(UserGoal.user_id == current_user.id).delete()
    for goal_id in payload.goal_ids:
        db.add(UserGoal(user_id=current_user.id, goal_id=goal_id))

    # Get or create onboarding record
    onboarding = db.query(UserOnboarding).filter(
        UserOnboarding.user_id == current_user.id
    ).first()

    now = datetime.now(timezone.utc)

    if payload.skip:
        status = OnboardingStatus.skipped
        completed_at = now
    else:
        status = OnboardingStatus.completed
        completed_at = now

    discussion_topics_str = [t.value for t in payload.discussion_topics]

    if onboarding:
        onboarding.experience_level = payload.experience_level
        onboarding.discussion_topics = discussion_topics_str
        onboarding.status = status
        onboarding.completed_at = completed_at
        onboarding.updated_at = now
    else:
        onboarding = UserOnboarding(
            user_id=current_user.id,
            experience_level=payload.experience_level,
            discussion_topics=discussion_topics_str,
            status=status,
            completed_at=completed_at,
        )
        db.add(onboarding)

    db.commit()
    db.refresh(onboarding)

    return OnboardingDataOut(
        status=onboarding.status,
        interest_ids=payload.interest_ids,
        goal_ids=payload.goal_ids,
        experience_level=onboarding.experience_level,
        discussion_topics=payload.discussion_topics,
        completed_at=onboarding.completed_at.isoformat() if onboarding.completed_at else None,
    )
