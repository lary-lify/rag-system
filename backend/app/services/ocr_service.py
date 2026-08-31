"""
OCR Service - 可插拔的图片文字识别层。

设计目标：RAG 图文混排场景下，把图片里的文字提取出来回填进 chunk，
使图片内容可被检索问答。具体 OCR 引擎通过 Backend 抽象解耦：

- MockOCRBackend   : 演示用，不依赖任何外部引擎/密钥，读图片尺寸返回模拟识别文字
- TongyiVLBackend  : 接入通义 qwen-vl（DashScope 兼容 OpenAI 协议），沙箱需 TONGYI_API_KEY
- RapidOCRBackend  : 本地离线 OCR（rapidocr-onnxruntime），需 pip 安装并首次下载模型

通过 get_ocr_backend(name) 工厂获取实例，parser 只依赖 OCRBackend 协议，
切换引擎只需改一行（或在 config 里配 OCR_BACKEND）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class OCRBackend(Protocol):
    """OCR 后端协议：输入图片路径，返回识别到的纯文本（已合并换行）。"""

    name: str

    def ocr_image(self, image_path: str) -> str:
        ...


class MockOCRBackend:
    """演示后端：不调用任何真实引擎。

    真实读取图片尺寸，返回一段「模拟识别文字」，让整条
    「图片 -> OCR -> 文字入 chunk -> 切片」链路在没有密钥/引擎时也能跑通演示。
    """

    name = "mock"

    def ocr_image(self, image_path: str) -> str:
        try:
            from PIL import Image

            with Image.open(image_path) as im:
                width, height = im.size
                fmt = im.format or "未知"
            base = os.path.splitext(os.path.basename(image_path))[0]
            return (
                f"【模拟OCR识别结果】图片《{base}》（格式{fmt}，宽{width}高{height}）"
                f"中的文字内容如下：此处为演示占位文字，接入真实 OCR 引擎后"
                f"将替换为图片里实际印刷/绘制的文字。"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"MockOCR 无法读取图片 {image_path}: {e}")
            return f"【模拟OCR】无法读取图片 {image_path}：{e}"


class TongyiVLBackend:
    """通义 qwen-vl 后端：把图片发给 DashScope 多模态模型，要求返回图中全部文字。

    复用项目已有的 TONGYI_API_KEY / TONGYI_BASE_URL 配置。
    沙箱无 key 时不实例化即可，不影响其他后端。
    """

    name = "tongyi-vl"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "qwen-vl-max",
    ) -> None:
        self.api_key = api_key or settings.TONGYI_API_KEY
        self.base_url = base_url or settings.TONGYI_BASE_URL
        self.model = model
        if not self.api_key:
            raise ValueError("TongyiVLBackend 需要 TONGYI_API_KEY，当前未配置")

    def ocr_image(self, image_path: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        # 用 file:// 绝对路径或 base64 均可；这里用本地绝对路径（qwen-vl 支持)
        import base64

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请精确提取这张图片里的全部文字内容，"
                            "按原顺序输出，不要解释、不要翻译。若无可识别文字，"
                            "输出『[无文字]』。",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""


class RapidOCRBackend:
    """本地离线 OCR：rapidocr-onnxruntime，无需密钥。

    首次调用会触发模型下载（受沙箱网络影响）。lazy import，未安装时不报错。
    """

    name = "rapidocr"

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        except ImportError as e:
            raise RuntimeError(
                "RapidOCRBackend 需要安装 rapidocr-onnxruntime："
                "pip install rapidocr-onnxruntime"
            ) from e

    def ocr_image(self, image_path: str) -> str:
        result, _ = self._engine(image_path)
        if not result:
            return ""
        # result: List[[box, text, score], ...]
        lines = [item[1] for item in result if item and len(item) > 1]
        return "\n".join(lines)


_BACKENDS: dict[str, type[Any]] = {
    "mock": MockOCRBackend,
    "tongyi-vl": TongyiVLBackend,
    "rapidocr": RapidOCRBackend,
}


def get_ocr_backend(name: str = "mock", **kwargs: Any) -> OCRBackend:
    """工厂：按名字返回 OCR 后端实例。

    name 不在已知列表时回退到 mock，保证调用方永远拿到可用后端。
    """
    cls = _BACKENDS.get(name, MockOCRBackend)
    try:
        return cls(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"创建 OCR 后端 {name} 失败，回退 mock：{e}")
        return MockOCRBackend()
