"""PDF 需求文档解析器."""

from pathlib import Path
import fitz  # pymupdf


class PDFParser:
    """解析 PDF 文件，提取文本、表格和图片描述."""

    def __init__(self):
        self.image_counter = 0

    def parse(self, path: str | Path) -> str:
        """解析 PDF，返回 Markdown 格式结构化文本.

        Args:
            path: PDF 文件路径

        Returns:
            Markdown 格式的结构化文本
        """
        doc = fitz.open(str(path))
        md_lines: list[str] = []
        self.image_counter = 0

        for page_num, page in enumerate(doc, start=1):
            md_lines.append(f"\n<!-- Page {page_num} -->\n")

            # 提取文本块，保留层级结构
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))  # 按 y, x 排序

            for block in blocks:
                text = block[4].strip()
                if not text:
                    continue

                # 根据字体大小判断标题级别
                span = page.get_text("dict", clip=fitz.Rect(block[:4]))["blocks"]
                if span and "lines" in span[0]:
                    first_line = span[0]["lines"][0]
                    if first_line["spans"]:
                        font_size = first_line["spans"][0]["size"]
                        if font_size >= 20:
                            md_lines.append(f"\n# {text}\n")
                            continue
                        elif font_size >= 16:
                            md_lines.append(f"\n## {text}\n")
                            continue
                        elif font_size >= 13:
                            md_lines.append(f"\n### {text}\n")
                            continue

                md_lines.append(text)

            # 提取表格
            tables = page.find_tables()
            for table in tables.tables:
                md_lines.append("\n")
                md_lines.append(self._table_to_markdown(table))
                md_lines.append("\n")

            # 提取图片描述
            images = page.get_images(full=True)
            for _ in images:
                self.image_counter += 1
                md_lines.append(
                    f"\n> [Image {self.image_counter}] "
                    f"Screenshot/diagram on page {page_num}\n"
                )

        doc.close()
        return "\n".join(md_lines)

    def _table_to_markdown(self, table) -> str:
        """将表格转换为 Markdown 格式."""
        rows = table.extract()
        if not rows:
            return ""

        md_lines: list[str] = []
        # Header
        md_lines.append("| " + " | ".join(str(c) for c in rows[0]) + " |")
        # Separator
        md_lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
        # Data rows
        for row in rows[1:]:
            md_lines.append("| " + " | ".join(str(c) if c is not None else "" for c in row) + " |")

        return "\n".join(md_lines)
