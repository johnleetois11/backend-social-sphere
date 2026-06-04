from app.models.channel import Channel
from app.services.permission_service import has_role

def create_channel(db, user_id, data):
    if not has_role(db, user_id, data.group_id, ["owner", "admin"]):
        return None

    channel = Channel(
        group_id=data.group_id,
        name=data.name,
        type=data.type,
    )

    db.add(channel)
    db.commit()
    db.refresh(channel)

    return channel


def get_group_channels(db, group_id: int):
    return db.query(Channel).filter(Channel.group_id == group_id).all()
