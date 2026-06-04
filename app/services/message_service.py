from sqlalchemy.orm import Session
from app.models.message import Message
import logging

logger = logging.getLogger(__name__)

def save_message(db: Session, user_id: int, channel_id: int, content: str):
    try:
        message = Message(
            user_id=user_id,
            channel_id=channel_id,
            content=content
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        logger.info(f"Message saved: ID {message.id}, User {user_id}, Channel {channel_id}")
        return message
    except Exception as e:
        logger.error(f"Failed to save message: {e}")
        db.rollback()
        raise