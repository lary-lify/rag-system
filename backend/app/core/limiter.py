"""
Rate limiter configuration - 避免循环导入
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 全局限速器
limiter = Limiter(key_func=get_remote_address)
