-- ========================================
-- 迁移脚本：为已有知识库添加向量模型配置
-- 执行方式：mysql -u root -p rag_kb < migrate_add_embedding_model.sql
-- ========================================

-- 1. 添加字段（如果不存在）
SET @dbname = DATABASE();
SELECT COUNT(*) INTO @exist FROM information_schema.columns
WHERE table_schema = @dbname AND table_name = 'knowledge_bases' AND column_name = 'embedding_model';

SET @sqlstmt = IF(@exist = 0,
    'ALTER TABLE `knowledge_bases` ADD COLUMN `embedding_model` VARCHAR(64) NOT NULL DEFAULT ''text-embedding-v3'' AFTER `mode`',
    'SELECT ''Column embedding_model already exists'' AS status');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT COUNT(*) INTO @exist FROM information_schema.columns
WHERE table_schema = @dbname AND table_name = 'knowledge_bases' AND column_name = 'embedding_dimensions';

SET @sqlstmt = IF(@exist = 0,
    'ALTER TABLE `knowledge_bases` ADD COLUMN `embedding_dimensions` INT UNSIGNED NOT NULL DEFAULT 1536 AFTER `embedding_model`',
    'SELECT ''Column embedding_dimensions already exists'' AS status');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2. 为已有知识库设置默认值（如果为空）
UPDATE `knowledge_bases`
SET `embedding_model` = 'text-embedding-v3',
    `embedding_dimensions` = 1536
WHERE `embedding_model` IS NULL OR `embedding_model` = '';

-- 验证
SELECT id, name, embedding_model, embedding_dimensions FROM `knowledge_bases`;
