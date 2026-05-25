"""Excel 需求文档解析器."""

from pathlib import Path
import pandas as pd
from openpyxl import load_workbook


class ExcelParser:
    """解析 Excel 文件，提取表格数据和注释."""

    def parse(self, path: str | Path) -> str:
        """解析 Excel，返回 Markdown 格式结构化文本.

        Args:
            path: Excel 文件路径

        Returns:
            Markdown 格式的结构化文本
        """
        path = Path(path)
        md_lines: list[str] = [f"# Excel Document: {path.name}\n"]

        # 使用 openpyxl 读取以保留合并单元格信息
        wb = load_workbook(str(path), data_only=True)

        for sheet_name in wb.sheetnames:
            md_lines.append(f"\n## Sheet: {sheet_name}\n")
            ws = wb[sheet_name]

            # 提取合并单元格范围
            merged_ranges = list(ws.merged_cells.ranges)

            # 读取数据
            data = []
            for row in ws.iter_rows(values_only=False):
                row_data = []
                for cell in row:
                    value = cell.value
                    if value is not None:
                        row_data.append(str(value))
                    else:
                        row_data.append("")
                data.append(row_data)

            if not data:
                continue

            # 转换为 Markdown 表格
            max_cols = max(len(r) for r in data)
            for i, row in enumerate(data):
                # 补齐空列
                row = row + [""] * (max_cols - len(row))
                md_lines.append("| " + " | ".join(row) + " |")
                if i == 0:
                    md_lines.append("| " + " | ".join("---" for _ in row) + " |")

        wb.close()

        # 同时用 pandas 提取纯文本内容作为补充
        try:
            xl = pd.ExcelFile(str(path))
            for sheet_name in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
                if df.empty:
                    continue
                md_lines.append(f"\n### Text Content from {sheet_name}\n")
                for _, row in df.iterrows():
                    text = " ".join(str(v) for v in row if pd.notna(v))
                    if text.strip():
                        md_lines.append(text.strip())
        except Exception:
            pass

        return "\n".join(md_lines)
