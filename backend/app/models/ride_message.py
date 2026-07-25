"""Per-ride direct messages between a passenger and their driver.

Unlike the Joules assistant chat (one rolling thread per client, see
``app.models.chat``), this is a human-to-human thread scoped to a single ride:
the ride *is* the conversation. It opens when the ride is booked (CONFIRMED) and
stays usable until shortly after completion. ``read_at`` is stamped on the
*other* party's messages when a side opens the thread, so "unread" is always a
live COUNT and never a desynced counter.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class RideMessageSender(str, enum.Enum):
    client = "client"
    driver = "driver"


class RideMessageChannel(str, enum.Enum):
    """Which conversation a message belongs to. ``client`` is the passenger thread
    (the original one). ``internal`` is staff-only: the ride owner and the driver the
    ride was assigned to — the passenger must NEVER see it."""

    client = "client"
    internal = "internal"


class RideMessage(Base):
    __tablename__ = "ride_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ride_id: Mapped[int] = mapped_column(
        ForeignKey("rides.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender: Mapped[RideMessageSender] = mapped_column(
        pg_enum(RideMessageSender, name="ride_message_sender"), nullable=False
    )
    # Default `client` keeps every existing row (and the passenger endpoints) intact.
    channel: Mapped[RideMessageChannel] = mapped_column(
        pg_enum(RideMessageChannel, name="ride_message_channel"),
        nullable=False,
        default=RideMessageChannel.client,
        server_default=RideMessageChannel.client.value,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Stamped when the opposite party opens the thread; NULL = still unread by them.
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )

    __table_args__ = (
        Index("ix_ride_messages_ride_id_id", "ride_id", "id"),
        Index("ix_ride_messages_ride_channel_id", "ride_id", "channel", "id"),
    )
