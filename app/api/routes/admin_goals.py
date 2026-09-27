from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.models.goal import Goal
from app.models.user_goal import UserGoal
from app.api.routes.admin import log_admin_action
from app.api.schemas import AdminGoalIn, AdminGoalUpdateIn, AdminGoalOut

router = APIRouter()


# ------------------------------------------------------------------
# 1. GET /admin/goals — list with usage count
# ------------------------------------------------------------------
@router.get("/admin/goals")
def list_goals(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    usage_count = func.count(UserGoal.id).label("usage_count")
    rows = (
        db.query(Goal, usage_count)
        .outerjoin(UserGoal, UserGoal.goal_id == Goal.id)
        .group_by(Goal.id)
        .order_by(Goal.display_order, Goal.name)
        .all()
    )
    return [
        {
            "id": goal.id,
            "name": goal.name,
            "description": goal.description,
            "display_order": goal.display_order,
            "usage_count": count,
            "created_at": goal.created_at.isoformat() if goal.created_at else "",
        }
        for goal, count in rows
    ]


# ------------------------------------------------------------------
# 2. POST /admin/goals — create goal
# ------------------------------------------------------------------
@router.post("/admin/goals", response_model=AdminGoalOut)
def create_goal(
    data: AdminGoalIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Goal).filter(Goal.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Goal name already exists.")
    goal = Goal(
        name=data.name,
        description=data.description,
        display_order=data.display_order,
    )
    db.add(goal)
    log_admin_action(
        db, admin.id, "create_goal",
        target_type="goal", detail={"name": data.name},
    )
    db.commit()
    db.refresh(goal)
    return AdminGoalOut(
        id=goal.id,
        name=goal.name,
        description=goal.description,
        display_order=goal.display_order,
        created_at=goal.created_at.isoformat() if goal.created_at else "",
    )


# ------------------------------------------------------------------
# 3. PATCH /admin/goals/{goal_id} — update
# ------------------------------------------------------------------
@router.patch("/admin/goals/{goal_id}", response_model=AdminGoalOut)
def update_goal(
    goal_id: int,
    data: AdminGoalUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    goal = db.get(Goal, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    updates = data.model_dump(exclude_unset=True)
    # Check name uniqueness if changing name
    if "name" in updates and updates["name"] != goal.name:
        existing = db.query(Goal).filter(Goal.name == updates["name"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Goal name already exists.")
    for field, value in updates.items():
        setattr(goal, field, value)
    log_admin_action(
        db, admin.id, "update_goal",
        target_type="goal", target_id=goal_id, detail=updates,
    )
    db.commit()
    db.refresh(goal)
    return AdminGoalOut(
        id=goal.id,
        name=goal.name,
        description=goal.description,
        display_order=goal.display_order,
        created_at=goal.created_at.isoformat() if goal.created_at else "",
    )


# ------------------------------------------------------------------
# 4. DELETE /admin/goals/{goal_id} — delete
# ------------------------------------------------------------------
@router.delete("/admin/goals/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    goal = db.get(Goal, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    log_admin_action(
        db, admin.id, "delete_goal",
        target_type="goal", target_id=goal_id,
        detail={"name": goal.name},
    )
    db.delete(goal)
    db.commit()
    return {"status": "deleted"}
