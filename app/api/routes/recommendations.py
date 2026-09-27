"""
Recommendations API routes.

Endpoints:
- GET /me/recommended-sessions - Sessions matching user's interests/onboarding
- GET /me/recommended-groups   - Groups matching user's interests/goals
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.session import Session as SessionModel
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.interest import Interest
from app.models.user_interest import UserInterest
from app.models.user_goal import UserGoal
from app.models.goal import Goal
from app.models.user_onboarding import UserOnboarding
from app.models.user_agenda import UserAgenda
from app.api.schemas import SessionOut, GroupOut


router = APIRouter(dependencies=[require_feature("recommendations")])


def _user_to_speaker_brief(user: User) -> dict:
    """Convert User to brief dict for session responses."""
    return {
        "user_id": user.id,
        "full_name": user.full_name or "Unknown",
        "company": user.company,
        "avatar_url": user.avatar_url,
    }


def _session_to_out(session: SessionModel) -> dict:
    """Convert Session model to SessionOut dict."""
    return {
        "id": session.id,
        "title": session.title,
        "description": session.description,
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat(),
        "type": session.type,
        "topic_tags": session.topic_tags,
        "image_url": session.image_url,
        "venue": session.venue,
        "speakers": [_user_to_speaker_brief(u) for u in session.speakers],
    }


def _calculate_session_score(
    session: SessionModel,
    user_interest_ids: set[int],
    interest_names: set[str],
    discussion_topics: set[str],
) -> int:
    """
    Calculate relevance score for a session based on user's interests and discussion topics.

    Scoring:
    - Primary: +5 points per direct interest match via session.interests
    - Secondary: +2 points per topic_tag matching interest name (fallback)
    - +1 point per matching discussion topic
    """
    score = 0

    # Primary: Direct interest matches via relationship
    if session.interests:
        session_interest_ids = {interest.id for interest in session.interests}
        matching_interests = user_interest_ids & session_interest_ids
        score += len(matching_interests) * 5

    # Secondary: Fallback to topic_tags matching interest names
    if session.topic_tags:
        session_tags_lower = {tag.lower() for tag in session.topic_tags}
        for interest in interest_names:
            interest_lower = interest.lower()
            for tag in session_tags_lower:
                if interest_lower in tag or tag in interest_lower:
                    score += 2
                    break

        # Match against discussion topics
        for topic in discussion_topics:
            topic_lower = topic.lower().replace("_", " ")
            for tag in session_tags_lower:
                if topic_lower in tag or tag in topic_lower:
                    score += 1
                    break

    return score


def _calculate_group_score(
    group: Group,
    user_interest_ids: set[int],
    interest_names: set[str],
    goal_names: set[str],
) -> int:
    """
    Calculate relevance score for a group based on user's interests and goals.

    Scoring:
    - Primary: +5 points per direct interest match via group.interests
    - Secondary: +2 points for ref_key match, +1 for title match (fallback)
    - +1 point per goal match in title/description
    """
    score = 0

    # Primary: Direct interest matches via relationship
    if group.interests:
        group_interest_ids = {interest.id for interest in group.interests}
        matching_interests = user_interest_ids & group_interest_ids
        score += len(matching_interests) * 5

    # Secondary: Fallback to ref_key and title matching
    ref_key_lower = group.ref_key.lower()
    title_lower = group.title.lower()
    desc_lower = (group.description or "").lower()

    for interest in interest_names:
        interest_lower = interest.lower()
        # Check ref_key (e.g., "interest:fintech" matches "FinTech")
        if interest_lower in ref_key_lower:
            score += 2
        elif interest_lower in title_lower:
            score += 1

    # Match goals against title and description
    for goal in goal_names:
        goal_lower = goal.lower()
        goal_words = goal_lower.split()
        for word in goal_words:
            if len(word) > 3 and (word in title_lower or word in desc_lower):
                score += 1
                break

    return score


def _get_member_count(db: Session, group_id: int) -> int:
    """Get member count for a single group."""
    return db.query(func.count(GroupMember.id)).filter(GroupMember.group_id == group_id).scalar() or 0


@router.get("/me/recommended-sessions", response_model=list[SessionOut])
def get_recommended_sessions(
    limit: int = Query(20, ge=1, le=50, description="Maximum number of sessions to return"),
    exclude_agenda: bool = Query(True, description="Exclude sessions already in user's agenda"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get personalized session recommendations based on user's interests and onboarding data.

    Sessions are scored by matching their topic_tags against:
    - User's selected interests (via direct relationship - primary)
    - User's discussion topics from onboarding

    Returns sessions sorted by relevance score (highest first).
    Falls back to upcoming sessions if no personalized matches found.
    """
    # Get user's interest IDs and names
    interest_rows = db.execute(
        select(Interest.id, Interest.name)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .where(UserInterest.user_id == current_user.id)
    ).all()
    user_interest_ids = {row.id for row in interest_rows}
    interest_names = {row.name for row in interest_rows}

    # Get user's discussion topics from onboarding
    onboarding = db.execute(
        select(UserOnboarding).where(UserOnboarding.user_id == current_user.id)
    ).scalar_one_or_none()

    discussion_topics: set[str] = set()
    if onboarding and onboarding.discussion_topics:
        discussion_topics = set(onboarding.discussion_topics)

    # Get sessions to exclude (user's agenda)
    agenda_session_ids: list[int] = []
    if exclude_agenda:
        agenda_session_ids = list(db.execute(
            select(UserAgenda.session_id).where(UserAgenda.user_id == current_user.id)
        ).scalars().all())

    # Build base query for sessions
    base_query = (
        select(SessionModel)
        .options(
            joinedload(SessionModel.venue),
            selectinload(SessionModel.speakers),
            selectinload(SessionModel.interests),
        )
    )

    if agenda_session_ids:
        base_query = base_query.where(SessionModel.id.notin_(agenda_session_ids))

    # Try personalized recommendations first
    if user_interest_ids or discussion_topics:
        # Get sessions that have interests or topic_tags
        sessions = db.execute(base_query).unique().scalars().all()

        # Score and rank sessions
        scored_sessions: list[tuple[int, SessionModel]] = []
        for session in sessions:
            score = _calculate_session_score(
                session, user_interest_ids, interest_names, discussion_topics
            )
            if score > 0:
                scored_sessions.append((score, session))

        # Sort by score (descending), then by start_time
        scored_sessions.sort(key=lambda x: (-x[0], x[1].start_time))

        if scored_sessions:
            result = [_session_to_out(session) for _, session in scored_sessions[:limit]]
            return result

    # Fallback: return upcoming sessions sorted by start_time
    fallback_query = base_query.order_by(SessionModel.start_time).limit(limit)
    fallback_sessions = db.execute(fallback_query).unique().scalars().all()

    return [_session_to_out(session) for session in fallback_sessions]


@router.get("/me/recommended-groups", response_model=list[GroupOut])
def get_recommended_groups(
    limit: int = Query(20, ge=1, le=50, description="Maximum number of groups to return"),
    exclude_joined: bool = Query(True, description="Exclude groups user already joined"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get personalized group recommendations based on user's interests and goals.

    Groups are scored by matching their ref_key and title against:
    - User's selected interests (via direct relationship - primary)
    - User's goals from onboarding

    Returns groups sorted by relevance score (highest first).
    Falls back to popular groups if no personalized matches found.
    """
    # Get user's interest IDs and names
    interest_rows = db.execute(
        select(Interest.id, Interest.name)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .where(UserInterest.user_id == current_user.id)
    ).all()
    user_interest_ids = {row.id for row in interest_rows}
    interest_names = {row.name for row in interest_rows}

    # Get user's goal names
    goal_rows = db.execute(
        select(Goal.name)
        .join(UserGoal, UserGoal.goal_id == Goal.id)
        .where(UserGoal.user_id == current_user.id)
    ).scalars().all()
    goal_names = set(goal_rows)

    # Get groups to exclude (already joined)
    joined_group_ids: list[int] = []
    if exclude_joined:
        joined_group_ids = list(db.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == current_user.id)
        ).scalars().all())

    # Build base query for groups
    base_query = select(Group).options(selectinload(Group.interests))
    if joined_group_ids:
        base_query = base_query.where(Group.id.notin_(joined_group_ids))

    groups = db.execute(base_query).unique().scalars().all()

    def _calculate_match_percentage(group_interest_ids: set[int]) -> float | None:
        """Calculate match percentage based on common interests."""
        if not user_interest_ids:
            return None
        if not group_interest_ids:
            return 0.0
        common = len(group_interest_ids & user_interest_ids)
        return round((common / len(user_interest_ids)) * 100, 1)

    # Helper to convert groups to response with member counts and match percentage
    def groups_to_response(group_list: list[Group]) -> list[GroupOut]:
        result = []
        for group in group_list:
            group_interest_ids = {i.id for i in group.interests} if group.interests else set()
            result.append(
                GroupOut(
                    id=group.id,
                    group_type=group.group_type,
                    ref_key=group.ref_key,
                    title=group.title,
                    description=group.description,
                    member_count=_get_member_count(db, group.id),
                    match_percentage=_calculate_match_percentage(group_interest_ids),
                )
            )
        return result

    # Try personalized recommendations first
    if user_interest_ids or goal_names:
        scored_groups: list[tuple[int, Group]] = []
        for group in groups:
            score = _calculate_group_score(
                group, user_interest_ids, interest_names, goal_names
            )
            if score > 0:
                scored_groups.append((score, group))

        # Sort by score (descending), then by title
        scored_groups.sort(key=lambda x: (-x[0], x[1].title))

        if scored_groups:
            return groups_to_response([g for _, g in scored_groups[:limit]])

    # Fallback: return groups sorted by member count (most popular first)
    groups_with_counts = [(group, _get_member_count(db, group.id)) for group in groups]
    groups_with_counts.sort(key=lambda x: (-x[1], x[0].title))

    return groups_to_response([g for g, _ in groups_with_counts[:limit]])
