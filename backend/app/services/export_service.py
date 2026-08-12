"""
Export Service - Excel/CSV data export with token details.
Used for conversation history export, audit log export, etc.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from fastapi import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


def _calc_chat_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * settings.DEEPSEEK_INPUT_TOKEN_PRICE
        + output_tokens * settings.DEEPSEEK_OUTPUT_TOKEN_PRICE,
        6,
    )


async def export_conversations_to_excel(
    conversation_id: int | None = None,
    user_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db=None,
) -> Response:
    """
    Export conversations + messages to Excel.
    
    Required columns per requirement:
      - Question text
      - Answer text
      - Input tokens
      - Output tokens
      - Total tokens
      - Estimated cost
      - Timestamp
      - Source chunk references
    """
    import pandas as pd
    from sqlalchemy import select
    from app.models.conversation import Conversation
    from app.models.message import Message

    query = select(Message).join(Conversation).order_by(Message.created_at.desc())

    if conversation_id:
        query = query.where(Message.conversation_id == conversation_id)
    if user_id:
        query = query.where(Message.user_id == user_id)
    if start_date:
        query = query.where(Message.created_at >= start_date)
    if end_date:
        query = query.where(Message.created_at <= end_date)

    result = await db.execute(query)
    messages = result.scalars().all()

    rows = []
    for msg in messages:
        total_tok = msg.input_tokens + msg.output_tokens
        cost = _calc_chat_cost(msg.input_tokens, msg.output_tokens)
        # Format source chunks as readable string
        source_str = ""
        if msg.source_chunks:
            try:
                sources = msg.source_chunks if isinstance(msg.source_chunks, list) else []
                parts = [f"Chunk {s.get('chunk_id', '?')} (score={s.get('score', 0)})" for s in sources]
                source_str = "; ".join(parts) if parts else ""
            except Exception:
                source_str = str(msg.source_chunks)[:200]

        rows.append({
            "Conversation ID": msg.conversation_id,
            "Question": msg.question,
            "Answer": msg.answer[:2000] + "..." if len(msg.answer or "") > 2000 else (msg.answer or ""),
            "Input Tokens": msg.input_tokens,
            "Output Tokens": msg.output_tokens,
            "Total Tokens": total_tok,
            "Est. Cost (CNY)": cost,
            "Source Chunks": source_str,
            "Created At": str(msg.created_at),
        })

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Conversations", index=False)
        # Auto-adjust column widths
        ws = writer.sheets["Conversations"]
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_length + 2, 80)

    output.seek(0)
    filename = f"conversations_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
