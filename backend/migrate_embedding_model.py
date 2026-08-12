"""
迁移脚本：为已有知识库添加向量模型配置
运行方式：cd backend && python migrate_embedding_model.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import text
from app.core.database import AsyncSessionLocal


async def migrate():
    """为已有知识库添加向量模型配置"""
    db = AsyncSessionLocal()
    try:
        # 检查字段是否存在
        result = await db.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'knowledge_bases'
            AND column_name = 'embedding_model'
        """))
        row = result.fetchone()
        if row[0] == 0:
            print("[migrate] 添加 embedding_model 字段...")
            await db.execute(text("""
                ALTER TABLE `knowledge_bases`
                ADD COLUMN `embedding_model` VARCHAR(64) NOT NULL DEFAULT 'text-embedding-v3' AFTER `mode`
            """))
            await db.commit()
            print("[migrate] embedding_model 字段已添加")
        else:
            print("[migrate] embedding_model 字段已存在")

        # 检查 embedding_dimensions 字段
        result = await db.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'knowledge_bases'
            AND column_name = 'embedding_dimensions'
        """))
        row = result.fetchone()
        if row[0] == 0:
            print("[migrate] 添加 embedding_dimensions 字段...")
            await db.execute(text("""
                ALTER TABLE `knowledge_bases`
                ADD COLUMN `embedding_dimensions` INT UNSIGNED NOT NULL DEFAULT 1536 AFTER `embedding_model`
            """))
            await db.commit()
            print("[migrate] embedding_dimensions 字段已添加")
        else:
            print("[migrate] embedding_dimensions 字段已存在")

        # 为已有知识库设置默认值
        result = await db.execute(text("""
            UPDATE `knowledge_bases`
            SET `embedding_model` = 'text-embedding-v3',
                `embedding_dimensions` = 1536
            WHERE `embedding_model` IS NULL OR `embedding_model` = ''
        """))
        await db.commit()
        print(f"[migrate] 已更新 {result.rowcount} 条知识库记录")

        # 验证
        result = await db.execute(text("SELECT id, name, embedding_model, embedding_dimensions FROM knowledge_bases"))
        rows = result.fetchall()
        print("\n[migrate] 当前知识库配置：")
        for row in rows:
            print(f"  - ID={row[0]}, 名称={row[1]}, 模型={row[2]}, 维度={row[3]}")

        print("\n[migrate] 迁移完成！")

    except Exception as e:
        print(f"[migrate] 迁移失败: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(migrate())
