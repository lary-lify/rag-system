-- ========================================
-- RAG Knowledge Base System - MySQL Init SQL
-- Database: rag_kb
-- Engine: InnoDB, UTF-8mb4
-- ========================================

CREATE DATABASE IF NOT EXISTS `rag_kb`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `rag_kb`;

-- ========================================
-- 1. users - User accounts (3 roles)
-- ========================================
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
    `id`          INT NOT NULL AUTO_INCREMENT,
    `username`    VARCHAR(64)  NOT NULL COMMENT 'Login name',
    `password_hash` VARCHAR(128) NOT NULL COMMENT 'bcrypt hashed password',
    `real_name`   VARCHAR(64)  NOT NULL DEFAULT '' COMMENT 'Display name',
    `email`       VARCHAR(128) NOT NULL DEFAULT '',
    `phone`       VARCHAR(32)  NOT NULL DEFAULT '',
    `dept_name`   VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Department name',
    `role`        ENUM('super_admin', 'dept_admin', 'user') NOT NULL DEFAULT 'user',
    `status`      ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    INDEX `idx_dept_role` (`dept_name`, `role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User accounts';

-- ========================================
-- 2. knowledge_bases - Knowledge base metadata
-- ========================================
DROP TABLE IF EXISTS `knowledge_bases`;
CREATE TABLE `knowledge_bases` (
    `id`            INT NOT NULL AUTO_INCREMENT,
    `name`          VARCHAR(128) NOT NULL,
    `description`   TEXT         NOT NULL DEFAULT '',
    `owner_id`      INT NOT NULL COMMENT 'Creator user ID',
    `mode`          ENUM('private','shared') NOT NULL DEFAULT 'private' COMMENT 'Access mode',
    `embedding_model` VARCHAR(64) NOT NULL DEFAULT 'text-embedding-v3' COMMENT 'Embedding model name',
    `embedding_dimensions` INT NOT NULL DEFAULT 1536 COMMENT 'Vector dimensions',
    `doc_count`     INT NOT NULL DEFAULT 0 COMMENT 'Document count cache',
    `chunk_count`   INT NOT NULL DEFAULT 0 COMMENT 'Total chunk count cache',
    `is_deleted`    TINYINT(1)   NOT NULL DEFAULT 0,
    `deleted_at`    DATETIME     NULL DEFAULT NULL,
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_owner` (`owner_id`),
    INDEX `idx_mode` (`mode`),
    INDEX `idx_deleted` (`is_deleted`),
    INDEX `idx_updated_at` (`updated_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Knowledge bases';

-- ========================================
-- 3. kb_permissions - KB-level permission control
-- ========================================
DROP TABLE IF EXISTS `kb_permissions`;
CREATE TABLE `kb_permissions` (
    `id`                INT NOT NULL AUTO_INCREMENT,
    `kb_id`             INT NOT NULL,
    `user_id`           INT NOT NULL,
    `permission_level`  ENUM('read','upload','admin') NOT NULL DEFAULT 'read',
    `created_by`        INT NOT NULL COMMENT 'Grantor user ID',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_kb_user` (`kb_id`, `user_id`),
    INDEX `idx_user` (`user_id`),
    CONSTRAINT `fk_perm_kb` FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_perm_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Knowledge base permissions';

-- ========================================
-- 4. documents - Uploaded document metadata
-- ========================================
DROP TABLE IF EXISTS `documents`;
CREATE TABLE `documents` (
    `id`                  INT NOT NULL AUTO_INCREMENT,
    `kb_id`               INT NOT NULL,
    `filename`            VARCHAR(255) NOT NULL COMMENT 'Stored filename (UUID-based)',
    `original_filename`   VARCHAR(255) NOT NULL COMMENT 'Original upload filename',
    `file_size`           BIGINT       NOT NULL DEFAULT 0 COMMENT 'File size in bytes',
    `file_type`           VARCHAR(16)  NOT NULL COMMENT 'Extension: pdf/docx/pptx/txt/md',
    `uploader_id`         INT NOT NULL,
    `chunk_strategy`      VARCHAR(32)  NOT NULL DEFAULT 'fixed_token',
    `chunk_params`        JSON         NOT NULL COMMENT '{"chunk_size":512,"overlap":128,...}',
    `chunk_count`         INT NOT NULL DEFAULT 0,
    `status`              ENUM('pending','parsing','embedding','completed','failed') NOT NULL DEFAULT 'pending',
    `error_msg`           TEXT         NOT NULL DEFAULT '',
    `is_deleted`          TINYINT(1)   NOT NULL DEFAULT 0,
    `deleted_at`          DATETIME     NULL DEFAULT NULL,
    `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_kb_id` (`kb_id`, `is_deleted`),
    INDEX `idx_uploader` (`uploader_id`),
    INDEX `idx_status` (`status`),
    CONSTRAINT `fk_doc_kb` FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_doc_user` FOREIGN KEY (`uploader_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Document metadata';

-- ========================================
-- 5. chunks - Text chunks after splitting
-- ========================================
DROP TABLE IF EXISTS `chunks`;
CREATE TABLE `chunks` (
    `id`              BIGINT NOT NULL AUTO_INCREMENT,
    `document_id`     INT    NOT NULL,
    `kb_id`           INT    NOT NULL,
    `content`         TEXT            NOT NULL,
    `chunk_index`     INT             NOT NULL COMMENT 'Sequence number in document',
    `token_count`     INT    NOT NULL DEFAULT 0,
    `metadata`        JSON            NOT NULL DEFAULT '{}' COMMENT 'page_num/heading/etc',
    `milvus_id`       BIGINT NULL DEFAULT NULL COMMENT 'Corresponding Milvus entity ID',
    `is_deleted`      TINYINT(1)      NOT NULL DEFAULT 0,
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_milvus_id` (`milvus_id`),
    INDEX `idx_document_id` (`document_id`, `is_deleted`),
    INDEX `idx_kb_id` (`kb_id`, `is_deleted`),
    FULLTEXT KEY `ft_content` (`content`) WITH PARSER ngram,
    CONSTRAINT `fk_chunk_doc` FOREIGN KEY (`document_id`) REFERENCES `documents`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chunk_kb` FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Text chunks';

-- ========================================
-- 6. conversations - Chat sessions
-- ========================================
DROP TABLE IF EXISTS `conversations`;
CREATE TABLE `conversations` (
    `id`          INT  NOT NULL AUTO_INCREMENT,
    `user_id`     INT  NOT NULL,
    `title`       VARCHAR(200)  NOT NULL DEFAULT '' COMMENT 'Auto-generated or user-set title',
    `kb_ids`      JSON          NOT NULL DEFAULT '[]' COMMENT 'Associated KB IDs for this session',
    `message_count` INT NOT NULL DEFAULT 0,
    `is_deleted`  TINYINT(1)    NOT NULL DEFAULT 0,
    `deleted_at`  DATETIME      NULL DEFAULT NULL,
    `created_at`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_user_del` (`user_id`, `is_deleted`),
    CONSTRAINT `fk_conv_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Chat conversations';

-- ========================================
-- 7. messages - Q&A message records
-- ========================================
DROP TABLE IF EXISTS `messages`;
CREATE TABLE `messages` (
    `id`              INT NOT NULL AUTO_INCREMENT,
    `conversation_id` INT NOT NULL,
    `user_id`         INT NOT NULL,
    `question`        TEXT         NOT NULL COMMENT 'User question text',
    `answer`          MEDIUMTEXT   NULL DEFAULT '' COMMENT 'LLM response text (streamed)',
    `source_chunks`   JSON         NOT NULL DEFAULT '[]' COMMENT 'Retrieved source chunk IDs and scores',
    `input_tokens`    INT NOT NULL DEFAULT 0,
    `output_tokens`   INT NOT NULL DEFAULT 0,
    `total_tokens`    INT NOT NULL DEFAULT 0 GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
    `feedback`        TINYINT      NULL DEFAULT NULL COMMENT '1=good, 0=bad, NULL=no feedback',
    `feedback_time`   DATETIME     NULL DEFAULT NULL COMMENT 'Feedback timestamp',
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_conversation` (`conversation_id`),
    INDEX `idx_user_time` (`user_id`, `created_at` DESC),
    INDEX `idx_feedback` (`feedback`),
    CONSTRAINT `fk_msg_conv` FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_msg_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Q&A messages';

-- ========================================
-- 8. token_usage - Token billing records (multi-dimensional)
-- ========================================
DROP TABLE IF EXISTS `token_usage`;
CREATE TABLE `token_usage` (
    `id`              BIGINT NOT NULL AUTO_INCREMENT,
    `type`            ENUM('embedding','chat') NOT NULL,
    `user_id`         INT    NOT NULL,
    `kb_id`           INT    NULL DEFAULT NULL,
    `document_id`     INT    NULL DEFAULT NULL,
    `conversation_id` INT    NULL DEFAULT NULL,
    `message_id`      INT    NULL DEFAULT NULL,
    `input_tokens`    INT    NOT NULL DEFAULT 0,
    `output_tokens`   INT    NOT NULL DEFAULT 0,
    `estimated_cost`  DECIMAL(12,6)  NOT NULL DEFAULT 0.000000 COMMENT 'Cost in CNY',
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_type_time` (`type`, `created_at`),
    INDEX `idx_user_type` (`user_id`, `type`),
    INDEX `idx_kb_type` (`kb_id`, `type`),
    INDEX `idx_date` (`created_at`),
    CONSTRAINT `fk_tok_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_tok_kb` FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_tok_doc` FOREIGN KEY (`document_id`) REFERENCES `documents`(`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_tok_conv` FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Token usage & cost tracking';

-- ========================================
-- 9. login_logs - Login audit trail
-- ========================================
DROP TABLE IF EXISTS `login_logs`;
CREATE TABLE `login_logs` (
    `id`          INT NOT NULL AUTO_INCREMENT,
    `user_id`     INT NOT NULL,
    `ip_address`  VARCHAR(45)  NOT NULL DEFAULT '' COMMENT 'IPv4/IPv6',
    `user_agent`  VARCHAR(512) NOT NULL DEFAULT '',
    `success`     TINYINT(1)   NOT NULL DEFAULT 1,
    `fail_reason` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Reason if failed',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_user_time` (`user_id`, `created_at` DESC),
    INDEX `idx_ip` (`ip_address`),
    CONSTRAINT `fk_login_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Login logs';

-- ========================================
-- 10. audit_logs - Full audit trail for all operations
-- ========================================
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
    `id`            INT NOT NULL AUTO_INCREMENT,
    `user_id`       INT NULL DEFAULT NULL COMMENT 'NULL for system actions',
    `action`        VARCHAR(64)  NOT NULL COMMENT 'create/update/delete/login/export/config_view/...',
    `resource_type` VARCHAR(32)  NOT NULL COMMENT 'user/kb/document/chunk/conversation/system_config',
    `resource_id`   INT NULL DEFAULT NULL,
    `detail`        JSON         NOT NULL DEFAULT '{}',
    `ip_address`    VARCHAR(45)  NOT NULL DEFAULT '',
    `user_agent`    VARCHAR(512) NOT NULL DEFAULT '',
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_action_time` (`action`, `created_at` DESC),
    INDEX `idx_resource` (`resource_type`, `resource_id`),
    INDEX `idx_user_audit` (`user_id`, `created_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Operation audit logs';
