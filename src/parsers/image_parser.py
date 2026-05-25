"""图片/截图需求文档解析器（OCR + Claude Vision）."""

from pathlib import Path
import base64
from io import BytesIO
from PIL import Image
import anthropic


class ImageParser:
    """解析图片文件，通过 Claude Vision API 提取需求内容."""

    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

    def parse(self, path: str | Path, api_key: str | None = None) -> str:
        """解析图片，返回 Markdown 格式结构化文本.

        优先使用 Claude Vision API 进行高精度 OCR 和理解。
        如果 API 不可用，则回退到基础图片信息。

        Args:
            path: 图片文件路径
            api_key: Anthropic API key（可选，也可在初始化时传入）

        Returns:
            Markdown 格式的结构化文本
        """
        path = Path(path)

        # 读取图片
        with Image.open(path) as img:
            width, height = img.size
            format_name = img.format or "Unknown"

            # 转为 base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

        md_lines: list[str] = [
            f"# Image: {path.name}\n",
            f"> Image info: {width}x{height}, format: {format_name}\n",
        ]

        # 尝试使用 Claude Vision API
        client = self.client
        if api_key and not client:
            client = anthropic.Anthropic(api_key=api_key)

        if client:
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6-20251001",
                    max_tokens=4096,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": image_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "请仔细阅读这张需求文档截图，提取其中的所有需求内容。"
                                        "以结构化的 Markdown 格式输出，保留标题层级、表格和列表。"
                                        "如果是流程图或架构图，请描述其结构和关键节点。"
                                    ),
                                },
                            ],
                        }
                    ],
                )

                content = response.content[0].text if response.content else ""
                md_lines.append("\n## OCR Extracted Content\n")
                md_lines.append(content)

            except Exception as e:
                md_lines.append(f"\n> [Warning] Vision API failed: {e}\n")
                md_lines.append(
                    "> Please manually transcribe this image or provide API key.\n"
                )
        else:
            md_lines.append(
                "\n> [Note] No API key provided. "
                "Set ANTHROPIC_API_KEY env var or pass api_key parameter.\n"
            )

        return "\n".join(md_lines)

    def parse_batch(self, paths: list[str | Path], api_key: str | None = None) -> list[str]:
        """批量解析多张图片.

        Args:
            paths: 图片路径列表
            api_key: Anthropic API key

        Returns:
            每张图片解析后的 Markdown 文本列表
        """
        return [self.parse(p, api_key) for p in paths]
