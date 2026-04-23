-- MySQL 初始化脚本
-- 确保字符集正确

ALTER DATABASE telegram_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 确认数据库创建成功
SELECT 'Database telegram_bot initialized.' AS status;
