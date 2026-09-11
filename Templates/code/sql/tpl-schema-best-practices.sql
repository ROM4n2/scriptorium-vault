-- =============================================================================
-- Production-Grade MySQL Schema Best Practices Template
-- Includes BIGINT PK, created_at/updated_at, deleted_at (soft delete),
-- proper index naming, UTF8MB4 charset, and InnoDB engine.
-- =============================================================================

CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `user_uuid` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '用户业务唯一标识',
    `username` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '用户名',
    `email` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '电子邮箱',
    `password_hash` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '密码哈希',
    `status` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '状态: 1-正常, 2-禁用, 3-注销',
    `version` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '乐观锁版本号',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT '软删除时间戳(NULL表示未删除)',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_uuid` (`user_uuid`),
    UNIQUE KEY `uk_email_deleted` (`email`, `deleted_at`),
    KEY `idx_username` (`username`),
    KEY `idx_status_created` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户基础信息表';
