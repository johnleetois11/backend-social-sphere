from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from fastapi import HTTPException

from app.models.direct_message import DirectMessage
from app.models.user import User
from app.models.group_member import GroupMember
from app.services.ws_manager import manager


def _share_group(db: Session, user1_id: int, user2_id: int) -> bool:
    """Return True if both users share at least one group."""
    u1_groups = {m.group_id for m in db.query(GroupMember).filter_by(user_id=user1_id).all()}
    u2_groups = {m.group_id for m in db.query(GroupMember).filter_by(user_id=user2_id).all()}
    return bool(u1_groups & u2_groups)


def get_dm_history(db: Session, user_id: int, peer_id: int, skip: int = 0, limit: int = 50):
    if not _share_group(db, user_id, peer_id):
        raise HTTPException(status_code=403, detail="You must share a group to message this user")

    msgs = (
        db.query(DirectMessage)
        .filter(
            or_(
                and_(DirectMessage.sender_id == user_id, DirectMessage.receiver_id == peer_id),
                and_(DirectMessage.sender_id == peer_id, DirectMessage.receiver_id == user_id),
            )
        )
        .order_by(DirectMessage.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Mark received messages as read
    for m in msgs:
        if m.receiver_id == user_id and not m.is_read:
            m.is_read = True
    db.commit()

    return msgs


def save_dm(db: Session, sender_id: int, receiver_id: int, content: str, message_type: str = "text"):
    if not _share_group(db, sender_id, receiver_id):
        raise HTTPException(status_code=403, detail="You must share a group to message this user")

    msg = DirectMessage(
        sender_id=sender_id,
        receiver_id=receiver_id,
        content=content,
        message_type=message_type,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_conversations(db: Session, user_id: int):
    """Return list of recent DM conversations for a user."""
    # Get all users this user has exchanged messages with
    sent = db.query(DirectMessage.receiver_id).filter_by(sender_id=user_id).distinct()
    received = db.query(DirectMessage.sender_id).filter_by(receiver_id=user_id).distinct()
    peer_ids = {r[0] for r in sent} | {r[0] for r in received}

    result = []
    for peer_id in peer_ids:
        peer = db.query(User).filter(User.id == peer_id).first()
        if not peer:
            continue

        last_msg = (
            db.query(DirectMessage)
            .filter(
                or_(
                    and_(DirectMessage.sender_id == user_id, DirectMessage.receiver_id == peer_id),
                    and_(DirectMessage.sender_id == peer_id, DirectMessage.receiver_id == user_id),
                )
            )
            .order_by(DirectMessage.created_at.desc())
            .first()
        )

        unread = (
            db.query(DirectMessage)
            .filter_by(sender_id=peer_id, receiver_id=user_id, is_read=False)
            .count()
        )

        result.append({
            "user_id": peer.id,
            "username": peer.username,
            "full_name": peer.full_name,
            "avatar_url": peer.avatar_url,
            "last_message": last_msg.content if last_msg else "",
            "last_message_at": last_msg.created_at.isoformat() if last_msg else None,
            "last_message_type": last_msg.message_type if last_msg else "text",
            "unread_count": unread,
            "is_online": manager.is_online(peer.id),
        })

    result.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return result
