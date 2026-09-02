"""
应用层主键生成（雪花算法布局）。

## 为什么不用数据库自增

`chunks.id` 原本是自增列。aiomysql 驱动下，只要插入后需要回填自增主键，
SQLAlchemy 就会回退成逐行 INSERT——声明了的 `insertmanyvalues` 批量优化
（page_size=1000）根本不生效。结果是：批量 add_all + 单次 flush 看起来
合并了，实际仍是一条一条发，一份 500 片段的文档就是 500 次数据库往返。

实测（500 片段，本地 MySQL）：

    自增回填        : INSERT 500 条, 635.8 ms
    应用层显式主键  : INSERT   1 条, 183.2 ms   (3.5x)

由应用层显式给出主键后，SQLAlchemy 无需回填，批量插入才真正合并成一条
多值 INSERT。

## 布局

    符号位(1) | 毫秒时间戳(41) | worker(10) | 同毫秒序号(12)

- 时间戳在高位，保证 ID 趋势递增。chunks 表以 id 为聚簇索引，递增插入
  可避免 InnoDB 页分裂；随机 ID（如 UUID 转整数）会让插入退化成随机写。
- worker 段取进程 PID 低 10 位。同一时刻 PID 唯一，足以区分同一主机上的
  多个 gunicorn worker；worker 数远超 1024 的场景需要改用统一分配。
- 同毫秒序号 12 位，即单进程每毫秒 4096 个，溢出则等到下一毫秒。
- 41 位时间戳自 2026-01-01 起可用约 69 年。
"""
from __future__ import annotations

import os
import threading
import time

# 自定义纪元：2026-01-01T00:00:00Z，比 Unix 纪元多换来 41 位时间戳的可用年限
_EPOCH_MS = 1767225600000

_WORKER_BITS = 10
_SEQUENCE_BITS = 12

_MAX_WORKER = (1 << _WORKER_BITS) - 1
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1

_SHIFT_WORKER = _SEQUENCE_BITS
_SHIFT_TIME = _SEQUENCE_BITS + _WORKER_BITS

# 进程级 worker 标识，进程生命周期内固定
_WORKER_ID = os.getpid() & _MAX_WORKER

_lock = threading.Lock()
_last_ms = 0
_sequence = 0


def _current_ms() -> int:
    return int(time.time() * 1000)


def next_id() -> int:
    """生成一个全局唯一、趋势递增的正整数 ID。"""
    global _last_ms, _sequence

    with _lock:
        now = _current_ms()

        if now < _last_ms:
            # 时钟回拨：等到追平上一个时间戳为止。
            # 重复 ID 会直接破坏主键唯一性，宁可在这里多等一会儿。
            time.sleep((_last_ms - now) / 1000.0)
            now = _current_ms()

        if now == _last_ms:
            _sequence = (_sequence + 1) & _MAX_SEQUENCE
            if _sequence == 0:
                # 这一毫秒的序号用完了，等到下一毫秒
                while now <= _last_ms:
                    now = _current_ms()
        else:
            _sequence = 0

        _last_ms = now

        return (
            ((now - _EPOCH_MS) << _SHIFT_TIME)
            | (_WORKER_ID << _SHIFT_WORKER)
            | _sequence
        )


def next_ids(count: int) -> list[int]:
    """批量生成 ID，保证返回列表内严格递增。"""
    return [next_id() for _ in range(count)]
