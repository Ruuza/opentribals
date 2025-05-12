from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import BattleMessage
from app.schemas import MessageCreate, MessageDetail, MessageOut, MessagesList

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/received", response_model=MessagesList)
def list_received_messages(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    displayed: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get messages received by the current user.
    Can be filtered by displayed/unread status.
    """
    query = select(BattleMessage).where(BattleMessage.to_player_id == current_user.id)

    # Filter by displayed status if provided
    if displayed is not None:
        query = query.where(BattleMessage.displayed == displayed)

    # Apply pagination and ordering by creation date (newest first)
    query = query.order_by(BattleMessage.created_at.desc()).offset(skip).limit(limit)

    messages = session.exec(query).all()

    # Get total count for pagination
    count_query = select(BattleMessage).where(
        BattleMessage.to_player_id == current_user.id
    )
    if displayed is not None:
        count_query = count_query.where(BattleMessage.displayed == displayed)

    total_count = len(session.exec(count_query).all())

    return MessagesList(data=messages, count=total_count)


@router.get("/sent", response_model=MessagesList)
def list_sent_messages(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get messages sent by the current user.
    """
    query = (
        select(BattleMessage)
        .where(
            BattleMessage.from_player_id == current_user.id,
        )
        .order_by(BattleMessage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    messages = session.exec(query).all()

    # Get total count for pagination
    count_query = select(BattleMessage).where(
        BattleMessage.from_player_id == current_user.id
    )
    total_count = len(session.exec(count_query).all())

    return MessagesList(data=messages, count=total_count)


@router.get("/{message_id}", response_model=MessageDetail)
def get_message(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    message_id: int,
) -> Any:
    """
    Get a specific message by ID.
    User must be either the sender or receiver of the message.
    If user is the receiver, the message will be marked as read.
    """
    message = session.get(BattleMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Check if user is sender or receiver
    if (
        message.from_player_id != current_user.id
        and message.to_player_id != current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="You don't have permission to access this message"
        )

    # Mark as displayed if the current user is the recipient and it hasn't been displayed
    if message.to_player_id == current_user.id and not message.displayed:
        message.displayed = True
        session.add(message)
        session.commit()
        session.refresh(message)

    return message


@router.post("", response_model=MessageOut)
def send_message(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    message_create: MessageCreate,
) -> Any:
    """
    Send a new message to another player.
    """
    # Create the message
    new_message = BattleMessage(
        from_player_id=current_user.id,
        to_player_id=message_create.to_player_id,
        message=message_create.message,
        displayed=False,
    )

    session.add(new_message)
    session.commit()
    session.refresh(new_message)

    return new_message
