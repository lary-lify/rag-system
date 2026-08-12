"""
Daily Summary Service - 定时汇总任务
每日凌晨自动汇总前一天的token使用、问答统计等数据
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


async def run_daily_summary(target_date: date | None = None):
    """
    执行每日汇总任务
    
    Args:
        target_date: 要汇总的日期，默认为昨天
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    
    logger.info(f"[daily-summary] Starting daily summary for {target_date}")
    
    try:
        await _summarize_token_usage(target_date)
        await _summarize_qa_stats(target_date)
        await _summarize_hot_questions(target_date)
        logger.info(f"[daily-summary] Completed daily summary for {target_date}")
    except Exception as e:
        logger.error(f"[daily-summary] Failed: {e}", exc_info=True)


async def _summarize_token_usage(target_date: date):
    """汇总token使用数据"""
    from sqlalchemy import select, func, text
    from app.core.database import AsyncSessionLocal
    from app.models.token_usage import TokenUsage

    db = AsyncSessionLocal()
    try:
        # 查询指定日期的token使用数据
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        result = await db.execute(
            select(
                TokenUsage.type,
                TokenUsage.user_id,
                TokenUsage.kb_id,
                func.sum(TokenUsage.input_tokens).label("total_input"),
                func.sum(TokenUsage.output_tokens).label("total_output"),
                func.sum(TokenUsage.estimated_cost).label("total_cost"),
                func.count(TokenUsage.id).label("count"),
            ).where(
                TokenUsage.created_at >= start_time,
                TokenUsage.created_at < end_time,
            ).group_by(
                TokenUsage.type,
                TokenUsage.user_id,
                TokenUsage.kb_id,
            )
        )

        rows = result.fetchall()

        # 插入汇总数据
        for row in rows:
            await db.execute(text("""
                INSERT INTO daily_token_summary 
                    (summary_date, type, user_id, kb_id, total_input_tokens, total_output_tokens, total_cost, request_count)
                VALUES 
                    (:date, :type, :user_id, :kb_id, :input, :output, :cost, :count)
                ON DUPLICATE KEY UPDATE
                    total_input_tokens = VALUES(total_input_tokens),
                    total_output_tokens = VALUES(total_output_tokens),
                    total_cost = VALUES(total_cost),
                    request_count = VALUES(request_count)
            """), {
                "date": target_date,
                "type": row.type.value if hasattr(row.type, 'value') else row.type,
                "user_id": row.user_id,
                "kb_id": row.kb_id,
                "input": row.total_input or 0,
                "output": row.total_output or 0,
                "cost": float(row.total_cost or 0),
                "count": row.count or 0,
            })
        
        await db.commit()
        logger.info(f"[daily-summary] Token usage summarized: {len(rows)} records")
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[daily-summary] Token summary failed: {e}")
        raise
    finally:
        await db.close()


async def _summarize_qa_stats(target_date: date):
    """汇总问答统计数据"""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    db = AsyncSessionLocal()
    try:
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        # 查询每个知识库的问答统计（未评价默认为"有用"）
        # kb_ids 在 conversations 表中，需要 JOIN
        result = await db.execute(text("""
            SELECT
                c.kb_ids as kb_id_list,
                COUNT(*) as total_messages,
                SUM(CASE WHEN m.feedback = 1 OR m.feedback IS NULL THEN 1 ELSE 0 END) as good_feedback,
                SUM(CASE WHEN m.feedback = 0 THEN 1 ELSE 0 END) as bad_feedback,
                SUM(CASE WHEN JSON_LENGTH(m.source_chunks) > 0 THEN 1 ELSE 0 END) as hit_count
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.created_at >= :start_time AND m.created_at < :end_time
            GROUP BY c.kb_ids
        """), {"start_time": start_time, "end_time": end_time})
        
        rows = result.fetchall()
        
        for row in rows:
            # 解析kb_ids JSON数组
            kb_ids = []
            if row.kb_id_list:
                try:
                    import json
                    kb_ids = json.loads(row.kb_id_list) if isinstance(row.kb_id_list, str) else row.kb_id_list
                except:
                    kb_ids = []
            
            total = row.total_messages or 0
            good = row.good_feedback or 0
            bad = row.bad_feedback or 0
            hit = row.hit_count or 0
            
            feedback_total = good + bad
            feedback_rate = round(feedback_total / total * 100, 2) if total > 0 else 0
            satisfaction_rate = round(good / feedback_total * 100, 2) if feedback_total > 0 else 0
            hit_rate = round(hit / total * 100, 2) if total > 0 else 0
            
            # 为每个关联的kb_id插入记录
            kb_id_list = kb_ids if kb_ids else [None]
            for kb_id in kb_id_list:
                await db.execute(text("""
                    INSERT INTO daily_qa_summary 
                        (summary_date, kb_id, total_messages, good_feedback, bad_feedback, 
                         feedback_rate, satisfaction_rate, hit_count, hit_rate)
                    VALUES 
                        (:date, :kb_id, :total, :good, :bad, :feedback_rate, :satisfaction_rate, :hit, :hit_rate)
                    ON DUPLICATE KEY UPDATE
                        total_messages = VALUES(total_messages),
                        good_feedback = VALUES(good_feedback),
                        bad_feedback = VALUES(bad_feedback),
                        feedback_rate = VALUES(feedback_rate),
                        satisfaction_rate = VALUES(satisfaction_rate),
                        hit_count = VALUES(hit_count),
                        hit_rate = VALUES(hit_rate)
                """), {
                    "date": target_date,
                    "kb_id": kb_id,
                    "total": total,
                    "good": good,
                    "bad": bad,
                    "feedback_rate": feedback_rate,
                    "satisfaction_rate": satisfaction_rate,
                    "hit": hit,
                    "hit_rate": hit_rate,
                })
        
        await db.commit()
        logger.info(f"[daily-summary] QA stats summarized: {len(rows)} records")
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[daily-summary] QA stats summary failed: {e}")
        raise
    finally:
        await db.close()


async def _summarize_hot_questions(target_date: date):
    """汇总热门问题"""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    db = AsyncSessionLocal()
    try:
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        # 查询热门问题（按提问次数排序）
        result = await db.execute(text("""
            SELECT
                question,
                COUNT(*) as ask_count
            FROM messages
            WHERE created_at >= :start_time AND created_at < :end_time
            GROUP BY question
            ORDER BY ask_count DESC
            LIMIT 100
        """), {"start_time": start_time, "end_time": end_time})
        
        rows = result.fetchall()
        
        for row in rows:
            await db.execute(text("""
                INSERT INTO daily_hot_questions 
                    (summary_date, question, ask_count)
                VALUES 
                    (:date, :question, :count)
                ON DUPLICATE KEY UPDATE
                    ask_count = VALUES(ask_count)
            """), {
                "date": target_date,
                "question": row.question[:500] if row.question else "",
                "count": row.ask_count or 0,
            })
        
        await db.commit()
        logger.info(f"[daily-summary] Hot questions summarized: {len(rows)} records")
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[daily-summary] Hot questions summary failed: {e}")
        raise
    finally:
        await db.close()
