import secrets
import string

from sqlalchemy.orm import Session
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.channel import Channel


def _generate_invite_code(db: Session) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(8))
        if not db.query(Group).filter(Group.invite_code == code).first():
            return code


def create_group(db: Session, user_id: int, data):
    group = Group(
        name=data.name,
        description=data.description,
        purpose=data.purpose,
        type=data.type,
        owner_id=user_id,
        invite_code=_generate_invite_code(db),
    )

    db.add(group)
    db.commit()
    db.refresh(group)

    # Add creator as OWNER
    member = GroupMember(
        user_id=user_id,
        group_id=group.id,
        role="owner"
    )
    db.add(member)

    # Auto-create a default "general" text channel
    default_channel = Channel(
        group_id=group.id,
        name="general",
        type="text",
    )
    db.add(default_channel)

    db.commit()
    db.refresh(group)

    return group


def join_group(db: Session, user_id: int, group_id: int):
    existing = db.query(GroupMember).filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()

    if existing:
        return None

    member = GroupMember(
        user_id=user_id,
        group_id=group_id,
        role="member"
    )

    db.add(member)
    db.commit()

    return member


def join_by_code(db: Session, user_id: int, code: str):
    group = db.query(Group).filter(Group.invite_code == code.upper().strip()).first()
    if not group:
        return None, "Invalid invite code"

    existing = db.query(GroupMember).filter_by(user_id=user_id, group_id=group.id).first()
    if existing:
        return group, "already_member"

    member = GroupMember(user_id=user_id, group_id=group.id, role="member")
    db.add(member)
    db.commit()

    return group, None