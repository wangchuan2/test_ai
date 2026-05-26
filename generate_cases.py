#!/usr/bin/env python3
"""为财经数据平台文档第4、5点生成测试用例."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from docx import Document
from src.generators.llm_client import ClaudeClient
from src.generators.case_generator import TestCaseGenerator
from src.exporters.excel_exporter import ExcelExporter

API_KEY = "sk-1e5233f2b9b149719e125acc64aeba72"
DOC_PATH = Path("财经数据平台管理系统 —— VSCode 插件操作手册.docx")
OUTPUT_DIR = Path("data/test_cases")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_sections(doc_path: Path) -> dict[str, str]:
    """从 docx 中提取第4点和第5点的需求文本."""
    doc = Document(str(doc_path))
    all_text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    idx4 = idx5 = idx6 = -1
    for i, t in enumerate(all_text):
        if (t.startswith("4.") or t.startswith("4 ") or
            "数据查询" in t[:10]):
            idx4 = i
        elif (t.startswith("5.") or t.startswith("5 ") or
              "数据加工" in t[:10]):
            idx5 = i
        elif t.startswith("6.") or t.startswith("6 "):
            idx6 = i

    sections = {}
    if idx4 >= 0 and idx5 >= 0:
        sections["section4"] = "\n".join(all_text[idx4:idx5])
    else:
        sections["section4"] = ""

    if idx5 >= 0:
        end = idx6 if idx6 >= 0 else len(all_text)
        sections["section5"] = "\n".join(all_text[idx5:end])
    else:
        sections["section5"] = ""

    return sections


def generate_cases(section_name: str, requirement_text: str) -> list[dict]:
    """为单个章节生成测试用例."""
    print(f"\n{'=' * 60}")
    print(f"正在生成: {section_name}")
    print(f"{'=' * 60}")

    client = ClaudeClient(api_key=API_KEY, model="claude-sonnet-4-6-20251001")
    generator = TestCaseGenerator(client)

    cases = generator.generate(
        requirement_text=requirement_text,
        doc_version="1.0",
    )

    print(f"[OK] 生成完成: {len(cases)} 条用例")
    return cases


def main():
    print("=" * 60)
    print("财经数据平台 - 测试用例生成")
    print("=" * 60)

    print("\n[1/4] 正在解析文档...")
    sections = extract_sections(DOC_PATH)

    print(f"\n第4点(数据查询): {len(sections['section4'])} 字符")
    print(f"第5点(数据加工): {len(sections['section5'])} 字符")

    if not sections["section4"] and not sections["section5"]:
        print("[ERROR] 未能提取到第4、5点内容!")
        return

    all_cases = []
    module_cases = {}

    for section_key, title in [("section4", "4-数据查询"), ("section5", "5-数据加工")]:
        text = sections[section_key]
        if not text:
            print(f"[WARN] {title} 内容为空, 跳过")
            continue

        cases = generate_cases(title, text)

        for case in cases:
            case["module"] = title
            case["source"] = f"财经数据平台 v1.0 - {title}"

        all_cases.extend(cases)
        module_cases[title] = cases

        json_path = OUTPUT_DIR / f"{title}_cases.json"
        json_path.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"[SAVE] JSON: {json_path}")

    print("\n[3/4] 正在导出 Excel...")

    excel_path = OUTPUT_DIR / "财经数据平台_测试用例_第4-5点.xlsx"
    exporter = ExcelExporter()
    exporter.export(all_cases, excel_path, sheet_name="测试用例")
    print(f"[SAVE] Excel: {excel_path}")

    multi_path = OUTPUT_DIR / "财经数据平台_测试用例_分模块.xlsx"
    exporter2 = ExcelExporter()
    exporter2.export_multi_sheets(module_cases, multi_path)
    print(f"[SAVE] 分模块Excel: {multi_path}")

    print("\n" + "=" * 60)
    print(f"全部完成! 共生成 {len(all_cases)} 条测试用例")
    print("=" * 60)


if __name__ == "__main__":
    main()
