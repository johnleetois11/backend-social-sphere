from app.models.group_member import GroupMember

def is_member(db, user_id, group_id):
    return db.query(GroupMember).filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()