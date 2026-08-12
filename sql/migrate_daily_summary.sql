-- ========================================
-- 报表定时自动汇总表
-- 每日凌晨落库，存储每日汇总数据
-- ========================================
USE rag_kb;

-- 1. 每日Token使用汇总表
CREATE TABLE IF NOT EXISTS `daily_token_summary` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `summary_date` DATE NOT NULL COMMENT '汇总日期',
    `type` ENUM('embedding', 'chat', 'chunking') NOT NULL COMMENT '类型',
    `user_id` INT UNSIGNED NULL DEFAULT NULL COMMENT '用户ID',
    `kb_id` INT UNSIGNED NULL DEFAULT NULL COMMENT '知识库ID',
    `total_input_tokens` INT UNSIGNED NOT NULL DEFAULT 0,
    `total_output_tokens` INT UNSIGNED NOT NULL DEFAULT 0,
    `total_cost` DECIMAL(12,6) NOT NULL DEFAULT 0.000000 COMMENT '总费用(元)',
    `request_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '请求次数',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_date_type_user_kb` (`summary_date`, `type`, `user_id`, `kb_id`),
    INDEX `idx_date` (`summary_date`),
    INDEX `idx_user` (`user_id`),
    INDEX `idx_kb` (`kb_id`),
    INDEX `idx_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日Token使用汇总';

-- 2. 每日问答统计表
CREATE TABLE IF NOT EXISTS `daily_qa_summary` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `summary_date` DATE NOT NULL COMMENT '汇总日期',
    `kb_id` INT UNSIGNED NULL DEFAULT NULL COMMENT '知识库ID',
    `total_messages` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '总问答数',
    `good_feedback` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '好评数',
    `bad_feedback` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '差评数',
    `feedback_rate` DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT '反馈率(%)',
    `satisfaction_rate` DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT '满意率(%)',
    `hit_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '检索命中数',
    `hit_rate` DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT '命中率(%)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_date_kb` (`summary_date`, `kb_id`),
    INDEX `idx_date` (`summary_date`),
    INDEX `idx_kb` (`kb_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日问答统计汇总';

-- 3. 热门问题汇总表
CREATE TABLE IF NOT EXISTS `daily_hot_questions` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `summary_date` DATE NOT NULL COMMENT '汇总日期',
    `question` VARCHAR(500) NOT NULL COMMENT '问题',
    `ask_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '提问次数',
    `kb_id` INT UNSIGNED NULL DEFAULT NULL COMMENT '知识库ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_date` (`summary_date`),
    INDEX `idx_question` (`question`(100)),
    INDEX `idx_count` (`ask_count` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日热门问题';
