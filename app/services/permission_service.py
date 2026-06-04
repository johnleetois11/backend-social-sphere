from app.models.group_member import GroupMember

def has_role(db, user_id, group_id, allowed_roles):
    member = db.query(GroupMember).filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()

    if not member:
        return False

    return member.role in allowed_roles