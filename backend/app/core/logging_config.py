"""
集中式日志配置。

提供：彩色控制台输出 + 按天轮转的常规日志文件 + 独立的错误日志文件。
对齐脚手架 Base/Config/logConfig.py 的设计；日志目录落在项目根 logs/ 下。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from app.core.config import settings
from app.utils.path_utils import find_project_root


class ColoredFormatter(logging.Formatter):
    """带 ANSI 颜色的日志格式化器（仅用于控制台）。"""

    COLORS = {
        "DEBUG": "\033[36m",      # 青色
        "INFO": "\033[32m",       # 绿色
        "WARNING": "\033[33m",    # 黄色
        "ERROR": "\033[31m",      # 红色
        "CRITICAL": "\033[35m",   # 紫色
    }
    RESET = "\033[0m"

    def __init__(self, fmt=None, datefmt=None, use_color=True):
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record):
        log_message = super().format(record)
        if self.use_color and hasattr(record, "levelname"):
            color = self.COLORS.get(record.levelname)
            if color:
                log_message = color + log_message + self.RESET
        return log_message


def _log_level() -> int:
    return logging.DEBUG if settings.APP_DEBUG else logging.INFO


def setup_logging() -> None:
    """配置根日志器（幂等：已配置则跳过）。"""
    root_logger = logging.getLogger()

    if root_logger.handlers:
        return

    project_root = find_project_root()
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    log_format = logging.Formatter(fmt, datefmt=datefmt)
    colored_format = ColoredFormatter(fmt, datefmt=datefmt, use_color=True)

    level = _log_level()
    root_logger.setLevel(level)

    # 控制台
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(colored_format)
    root_logger.addHandler(console_handler)

    # 常规日志（按天轮转，保留 30 天）
    file_handler = TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # 错误日志（仅 ERROR 及以上）
    error_file_handler = TimedRotatingFileHandler(
        filename=log_dir / "app.error.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    error_file_handler.suffix = "%Y-%m-%d"
    error_file_handler.setFormatter(log_format)
    error_file_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_file_handler)

    logging.info(
        f"日志系统初始化完成（level={logging.getLevelName(level)}）；日志目录: {log_dir}"
    )
