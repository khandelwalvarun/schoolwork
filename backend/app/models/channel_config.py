from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ChannelConfig(Base):
    """Single-row config table for per-channel notification policy.

    One row, upserted. `config_json` is the full §5.3 YAML re-encoded as JSON.
    """

    __tablename__ = "channel_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config_json: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
