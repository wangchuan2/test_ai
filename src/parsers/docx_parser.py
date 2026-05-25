"""Word 需求文档解析器."""

from pathlib import Path
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


class DocxParser:
    """解析 Word 文件，提取文本、表格和图片."""

    def parse(self, path: str | Path) -> str:
        """解析 Word 文档，返回 Markdown 格式结构化文本.

        Args:
            path: Word 文件路径

        Returns:
            Markdown 格式的结构化文本
        """
        doc = Document(str(path))
        md_lines: list[str] = [f"# Document: {Path(path).name}\n"]
        image_counter = 0

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                paragraph = Paragraph(element, doc)
                text = paragraph.text.strip()
                if not text:
                    continue

                # 根据样式判断标题级别
                style_name = paragraph.style.name.lower() if paragraph.style else ""
                if "heading 1" in style_name or style_name == "title":
                    md_lines.append(f"\n# {text}\n")
                elif "heading 2" in style_name:
                    md_lines.append(f"\n## {text}\n")
                elif "heading 3" in style_name:
                    md_lines.append(f"\n### {text}\n")
                else:
                    md_lines.append(text)

            elif tag == "tbl":
                table = Table(element, doc)
                md_lines.append("\n")
                md_lines.append(self._table_to_markdown(table))
                md_lines.append("\n")

        # 统计图片
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_counter += 1

        if image_counter > 0:
            md_lines.append(f"\n> [Note] Document contains {image_counter} image(s)\n")

        return "\n".join(md_lines)

    def _table_to_markdown(self, table: Table) -> str:
        """将 Word 表格转换为 Markdown 格式."""
        md_lines: list[str] = []
        rows = list(table.rows)
        if not rows:
            return ""

        for i, row in enumerate(rows):
            cells = [cell.text.strip() for cell in row.cells]
            md_lines.append("| " + " | ".join(cells) + " |")
            if i == 0:
                md_lines.append("| " + " | ".join("---" for _ in cells) + " |")

        return "\n".join(md_lines)
