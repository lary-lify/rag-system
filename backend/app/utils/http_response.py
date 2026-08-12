"""
统一的 HTTP 响应封装（对齐脚手架 Base.RicUtils.httpUtils.HttpResponse）。

用法：
    return HttpResponse.ok(data=..., msg="success")
    return HttpResponse.error(msg="参数错误")
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


class HttpResponse:
    @staticmethod
    def ok(data: Any = None, msg: str = "success", code: int = 0):
        return JSONResponse(status_code=200, content={"code": code, "msg": msg, "data": data})

    @staticmethod
    def error(msg: str = "error", code: int = 1, status_code: int = 200):
        return JSONResponse(status_code=status_code, content={"code": code, "msg": msg, "data": None})
