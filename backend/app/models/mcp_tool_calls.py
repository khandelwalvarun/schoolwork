from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MCPToolCall(Base):
    """Audit trail for every MCP tool invocation — so the /notifications page can
    show what Dispatch / OpenClaw / Claude Desktop have been doing."""

    __tablename__ = "mcp_tool_calls"
    __table_args__ = (Index("idx_mcp_tool_calls_tool_time", "tool", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    arguments_json: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    result_preview: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
