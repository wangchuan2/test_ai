"""Test Case Generator MCP Server.

提供以下能力：
- Tools: 文档解析、用例生成、变更检测、Excel 导出
- Resources: 测试用例库、需求文档
- Prompts: 需求分析、用例生成、质量 review

Usage:
    python -m mcp_server.server
"""

import json
import os
from pathlib import Path

from fastmcp import FastMCP

# Import our modules
try:
    from src.parsers import PDFParser, ExcelParser, DocxParser, ImageParser
    from src.generators import ClaudeClient, TestCaseGenerator
    from src.exporters import ExcelExporter
    from src.analyzers import RequirementSplitter
    from src.diff_engine import DocumentDiffer, ImpactAnalyzer
    from src.validators import RuleEngine, QualityScorer
except ImportError:
    # 开发模式下：将项目根目录加入 sys.path（仅在需要时执行一次）
    import sys
    _project_root = str(Path(__file__).resolve().parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from src.parsers import PDFParser, ExcelParser, DocxParser, ImageParser
    from src.generators import ClaudeClient, TestCaseGenerator
    from src.exporters import ExcelExporter
    from src.analyzers import RequirementSplitter
    from src.diff_engine import DocumentDiffer, ImpactAnalyzer
    from src.validators import RuleEngine, QualityScorer

# ---- Server Setup ----

mcp = FastMCP(
    "test-case-generator",
    instructions=(
        "测试用例生成 MCP Server。帮助测试人员从需求文档自动生成、管理测试用例，"
        "支持 PDF/Excel/Word/图片等多种文档格式，并在需求变更时自动同步测试用例。"
    ),
)

DATA_DIR = Path(os.getenv("TCG_DATA_DIR", Path(__file__).parent.parent / "data"))
REQUIREMENTS_DIR = DATA_DIR / "requirements"
PARSED_DIR = DATA_DIR / "parsed"
TEST_CASES_DIR = DATA_DIR / "test_cases"

REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)
TEST_CASES_DIR.mkdir(parents=True, exist_ok=True)

# ---- Helpers ----

_client_instance: ClaudeClient | None = None


def _get_client() -> ClaudeClient:
    """获取 LLM 客户端（单例模式）.

    优先使用环境变量中的 API Key，未设置时返回 disabled 模式的客户端。
    多次调用返回同一实例，避免重复创建。
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = ClaudeClient()
    return _client_instance


def _save_parsed(doc_name: str, markdown: str) -> Path:
    """保存解析后的 Markdown。"""
    path = PARSED_DIR / f"{doc_name}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def _save_cases(doc_name: str, cases: list) -> Path:
    """保存测试用例 JSON。"""
    path = TEST_CASES_DIR / f"{doc_name}_cases.json"
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ====== TOOLS ======

@mcp.tool(
    name="parse_document",
    description="解析需求文档（PDF/Excel/Word/图片），提取为结构化 Markdown 文本",
)
def parse_document(file_path: str) -> str:
    """解析需求文档。

    Args:
        file_path: 文档文件路径（支持 .pdf, .xlsx, .xls, .docx, .png, .jpg, .jpeg）

    Returns:
        解析后的 Markdown 文本，包含标题层级、表格、图片说明
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    doc_name = path.stem

    if ext == ".pdf":
        parser = PDFParser()
    elif ext in (".xlsx", ".xls"):
        parser = ExcelParser()
    elif ext == ".docx":
        parser = DocxParser()
    elif ext in (".png", ".jpg", ".jpeg"):
        parser = ImageParser()
    else:
        return f"❌ 不支持的文件格式: {ext}"

    try:
        result = parser.parse(path)
        saved = _save_parsed(doc_name, result)
        return f"✅ 解析成功！\n📄 原始: {path}\n📝 输出: {saved}\n\n--- 内容摘要 ---\n{result[:2000]}..."
    except Exception as e:
        return f"❌ 解析失败: {type(e).__name__}: {e}"


@mcp.tool(
    name="split_requirement",
    description="将需求文档拆分为多个模块化的子需求，生成独立的 Markdown 文件",
)
def split_requirement(doc_name: str) -> str:
    """拆分需求文档为子需求。

    Args:
        doc_name: 已解析的需求文档名称（不含 .md 后缀）

    Returns:
        拆分报告 Markdown
    """
    md_path = PARSED_DIR / f"{doc_name}.md"
    if not md_path.exists():
        return f"❌ 未找到解析后的文档: {md_path}"

    text = md_path.read_text(encoding="utf-8")
    splitter = RequirementSplitter()
    modules = splitter.split(text, doc_name)

    output_dir = PARSED_DIR / "split" / doc_name
    paths = splitter.export_to_files(output_dir, doc_name)

    summary = splitter.get_module_summary()
    return (
        f"✅ 拆分完成！共 {len(modules)} 个模块\n"
        f"📁 输出目录: {output_dir}\n"
        f"📄 文件数: {len(paths)}\n\n{summary}"
    )


@mcp.tool(
    name="generate_test_cases",
    description="根据需求文档生成结构化测试用例",
)
def generate_test_cases(doc_name: str, use_split: bool = False) -> str:
    """生成测试用例。

    Args:
        doc_name: 已解析的需求文档名称
        use_split: 是否使用拆分后的子需求（如果已拆分）

    Returns:
        生成结果摘要
    """
    client = _get_client()
    generator = TestCaseGenerator(client)

    # 读取历史用例（如果存在）
    historical = []
    hist_dir = DATA_DIR / "historical_cases"
    if hist_dir.exists():
        for f in hist_dir.glob("*.xlsx"):
            historical.extend(ExcelExporter.read_historical_cases(f))

    if use_split:
        # 逐个模块生成
        split_dir = PARSED_DIR / "split" / doc_name
        if not split_dir.exists():
            return f"❌ 未找到拆分结果: {split_dir}"

        all_cases = []
        errors = []
        for md_file in sorted(split_dir.glob(f"{doc_name}_*.md")):
            text = md_file.read_text(encoding="utf-8")
            try:
                cases = generator.generate(text, historical)
                all_cases.extend(cases)
            except Exception as e:
                errors.append(f"[{md_file.name}]: {e}")

        _save_cases(doc_name, all_cases)
        result = f"✅ 批量生成完成！共 {len(all_cases)} 条用例（来自 {len(list(split_dir.glob('*.md')))} 个模块）"
        if errors:
            result += f"\n⚠️ 部分模块生成失败 ({len(errors)} 个):\n" + "\n".join(errors)
        return result

    else:
        md_path = PARSED_DIR / f"{doc_name}.md"
        if not md_path.exists():
            return f"❌ 未找到解析后的文档: {md_path}"

        text = md_path.read_text(encoding="utf-8")
        try:
            cases = generator.generate(text, historical)
            _save_cases(doc_name, cases)
            return f"✅ 生成完成！共 {len(cases)} 条用例\n📄 输出: {TEST_CASES_DIR / f'{doc_name}_cases.json'}"
        except Exception as e:
            return f"❌ 生成失败: {type(e).__name__}: {e}"


@mcp.tool(
    name="export_to_excel",
    description="将生成的测试用例导出为 Excel 文件",
)
def export_to_excel(doc_name: str, output_path: str | None = None) -> str:
    """导出测试用例到 Excel。

    Args:
        doc_name: 测试用例对应的文档名称
        output_path: 输出文件路径（可选，默认输出到 data/test_cases/）

    Returns:
        导出结果
    """
    cases_path = TEST_CASES_DIR / f"{doc_name}_cases.json"
    if not cases_path.exists():
        return f"❌ 未找到测试用例: {cases_path}"

    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    if not output_path:
        output_path = TEST_CASES_DIR / f"{doc_name}_test_cases.xlsx"

    exporter = ExcelExporter()
    try:
        result_path = exporter.export(cases, output_path)
        return f"✅ Excel 导出成功！\n📊 文件: {result_path}\n📋 用例数: {len(cases)}"
    except Exception as e:
        return f"❌ 导出失败: {type(e).__name__}: {e}"


@mcp.tool(
    name="detect_doc_changes",
    description="语义级检测需求文档变更，输出结构化差异报告（支持章节/表格/图片变更检测）",
)
def detect_doc_changes(doc_name: str, new_file_path: str) -> str:
    """语义级文档变更检测。

    Args:
        doc_name: 原始文档名称（用于对比基线）
        new_file_path: 新版本文档路径

    Returns:
        结构化变更检测报告
    """
    baseline_path = PARSED_DIR / f"{doc_name}.md"
    if not baseline_path.exists():
        return f"❌ 未找到基线文档: {baseline_path}"

    # 解析新文档
    result = parse_document(new_file_path)
    if result.startswith("❌"):
        return result

    new_doc_name = Path(new_file_path).stem
    new_parsed_path = PARSED_DIR / f"{new_doc_name}.md"

    baseline = baseline_path.read_text(encoding="utf-8")
    new_text = new_parsed_path.read_text(encoding="utf-8")

    # 使用语义级 Diff 引擎
    differ = DocumentDiffer(similarity_threshold=0.7)
    diff = differ.compare(baseline, new_text, doc_name=doc_name)

    # 保存差异结果 JSON
    diff_path = TEST_CASES_DIR / f"{doc_name}_diff.json"
    diff_path.write_text(
        json.dumps(diff.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成 Markdown 报告
    report_lines = [
        f"# 需求变更检测报告（语义级）\n",
        f"**文档**: {doc_name}",
        f"**风险等级**: {'🔴 高' if diff.risk_level == 'high' else '🟡 中' if diff.risk_level == 'medium' else '🟢 低'}",
        f"**章节总数**: {diff.summary.get('total', 0)}",
        f"**新增**: {diff.summary.get('added', 0)} | **删除**: {diff.summary.get('removed', 0)} | **修改**: {diff.summary.get('modified', 0)} | **未变**: {diff.summary.get('unchanged', 0)}\n",
        "## 详细变更\n",
    ]

    for change in diff.changes:
        icon = {
            "added": "🟢",
            "removed": "🔴",
            "modified": "🟡",
            "unchanged": "⚪",
        }.get(change.change_type.value, "⚪")

        report_lines.append(f"### {icon} [{change.change_type.value.upper()}] {change.title}")

        if change.change_type.value in ("modified",):
            report_lines.append(f"- 相似度: {change.similarity:.1%}")
            for detail in change.details:
                if "reason" in detail:
                    report_lines.append(f"- {detail['reason']}")
                elif "type" in detail:
                    report_lines.append(f"- {detail['type']}: {detail}")
        elif change.change_type.value == "added":
            report_lines.append(f"- 新增章节，需生成对应测试用例")
        elif change.change_type.value == "removed":
            report_lines.append(f"- 章节已删除，关联用例需废弃")

        report_lines.append("")

    if diff.summary.get("added", 0) > 0 or diff.summary.get("modified", 0) > 0:
        report_lines.append(f"\n⚠️ **建议**: 运行 `sync_test_cases(doc_name='{doc_name}', new_doc_name='{new_doc_name}')` 同步测试用例\n")
    else:
        report_lines.append("\n✅ 无影响现有用例的变更。\n")

    report = "\n".join(report_lines)

    # 保存报告
    report_path = TEST_CASES_DIR / f"{doc_name}_change_report.md"
    report_path.write_text(report, encoding="utf-8")

    return report + f"\n\n📄 差异数据: {diff_path}"


@mcp.tool(
    name="sync_test_cases",
    description="根据文档变更自动同步测试用例，标记新增/需review/废弃，生成同步报告",
)
def sync_test_cases(doc_name: str, new_doc_name: str) -> str:
    """根据文档变更同步测试用例。

    Args:
        doc_name: 原始文档名称（基线）
        new_doc_name: 新版本文档名称

    Returns:
        同步报告
    """
    # 加载差异结果
    diff_path = TEST_CASES_DIR / f"{doc_name}_diff.json"
    if not diff_path.exists():
        return f"❌ 未找到差异数据，请先运行 detect_doc_changes(doc_name='{doc_name}', new_file_path=...)"

    diff_data = json.loads(diff_path.read_text(encoding="utf-8"))
    from src.diff_engine import ChangeType, DiffResult, SectionDiff
    diff = DiffResult(
        doc_name=diff_data["doc_name"],
        old_version=diff_data["old_version"],
        new_version=diff_data["new_version"],
        risk_level=diff_data["risk_level"],
    )
    for c in diff_data["changes"]:
        diff.changes.append(
            SectionDiff(
                change_type=ChangeType(c["change_type"]),
                section_id=c["section_id"],
                title=c["title"],
                similarity=c.get("similarity", 0.0),
                details=c.get("details", []),
            )
        )

    # 加载现有用例
    cases_path = TEST_CASES_DIR / f"{doc_name}_cases.json"
    if not cases_path.exists():
        return f"❌ 未找到现有用例: {cases_path}"

    existing_cases = json.loads(cases_path.read_text(encoding="utf-8"))

    # 影响分析
    analyzer = ImpactAnalyzer()
    impact = analyzer.analyze(diff, existing_cases)

    # 保存影响分析结果
    impact_path = TEST_CASES_DIR / f"{doc_name}_impact.json"
    impact_path.write_text(
        json.dumps(impact.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 应用同步：更新用例状态
    updated_cases = existing_cases.copy()
    new_cases_to_generate: list[str] = []
    cases_to_review: list[str] = []
    cases_to_deprecate: list[str] = []

    for imp in impact.impacts:
        if imp.suggested_action == "add":
            new_cases_to_generate.append(imp.source_section)
        elif imp.suggested_action == "review":
            cases_to_review.append(imp.case_id)
            for case in updated_cases:
                if case.get("id") == imp.case_id:
                    case["status"] = "needs-review"
                    case["review_reason"] = imp.reason
        elif imp.suggested_action == "deprecate":
            cases_to_deprecate.append(imp.case_id)
            for case in updated_cases:
                if case.get("id") == imp.case_id:
                    case["status"] = "deprecated"
                    case["deprecate_reason"] = imp.reason

    # 保存更新后的用例
    updated_path = TEST_CASES_DIR / f"{new_doc_name}_cases_synced.json"
    updated_path.write_text(
        json.dumps(updated_cases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成同步报告
    report_lines = [
        f"# 测试用例同步报告\n",
        f"**文档**: {doc_name} → {new_doc_name}",
        f"**风险等级**: {impact.risk_level}",
        f"**影响用例数**: {impact.summary.get('total', 0)}\n",
        "## 操作摘要\n",
        f"| 操作 | 数量 |",
        f"|------|------|",
        f"| 新增用例 | {len(set(new_cases_to_generate))} |",
        f"| 需 Review | {len(set(cases_to_review))} |",
        f"| 废弃 | {len(set(cases_to_deprecate))} |",
        f"| 无影响 | {impact.summary.get('none', 0)} |\n",
    ]

    if new_cases_to_generate:
        report_lines.append("## 需新增用例的模块\n")
        for module in set(new_cases_to_generate):
            report_lines.append(f"- 🟢 {module}")
        report_lines.append("")

    if cases_to_review:
        report_lines.append("## 需 Review 的用例\n")
        for case_id in set(cases_to_review):
            # 找到对应的 reason
            reason = ""
            for imp in impact.impacts:
                if imp.case_id == case_id:
                    reason = imp.reason
                    break
            report_lines.append(f"- 🟡 {case_id}: {reason}")
        report_lines.append("")

    if cases_to_deprecate:
        report_lines.append("## 需废弃的用例\n")
        for case_id in set(cases_to_deprecate):
            reason = ""
            for imp in impact.impacts:
                if imp.case_id == case_id:
                    reason = imp.reason
                    break
            report_lines.append(f"- 🔴 {case_id}: {reason}")
        report_lines.append("")

    report_lines.append(f"\n📄 同步后用例: {updated_path}")
    report_lines.append(f"📊 影响分析: {impact_path}\n")

    if new_cases_to_generate:
        report_lines.append(f"> 💡 提示: 运行 `generate_test_cases(doc_name='{new_doc_name}')` 为新模块生成用例")

    report = "\n".join(report_lines)

    # 保存报告
    sync_report_path = TEST_CASES_DIR / f"{doc_name}_sync_report.md"
    sync_report_path.write_text(report, encoding="utf-8")

    return report


@mcp.tool(
    name="list_documents",
    description="列出已解析的需求文档",
)
def list_documents() -> str:
    """列出所有已解析的需求文档。"""
    files = sorted(PARSED_DIR.glob("*.md"))
    if not files:
        return "📭 暂无已解析的文档"

    lines = ["# 已解析的需求文档\n"]
    for f in files:
        size = f.stat().st_size
        lines.append(f"- 📄 {f.name} ({size / 1024:.1f} KB)")
    return "\n".join(lines)


@mcp.tool(
    name="list_test_cases",
    description="列出已生成的测试用例",
)
def list_test_cases() -> str:
    """列出所有已生成的测试用例。"""
    files = sorted(TEST_CASES_DIR.glob("*_cases.json"))
    if not files:
        return "📭 暂无已生成的测试用例"

    lines = ["# 已生成的测试用例\n"]
    for f in files:
        try:
            cases = json.loads(f.read_text(encoding="utf-8"))
            lines.append(f"- 📋 {f.stem}: {len(cases)} 条用例")
        except (json.JSONDecodeError, OSError) as e:
            lines.append(f"- ⚠️ {f.stem}: 读取失败 ({e})")
    return "\n".join(lines)


@mcp.tool(
    name="validate_cases",
    description="对测试用例进行规则校验，检查必填字段、格式、内容模式等",
)
def validate_cases(doc_name: str) -> str:
    """规则校验测试用例。

    Args:
        doc_name: 测试用例对应的文档名称

    Returns:
        校验报告
    """
    cases_path = TEST_CASES_DIR / f"{doc_name}_cases.json"
    if not cases_path.exists():
        return f"❌ 未找到测试用例: {cases_path}"

    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    engine = RuleEngine()
    result = engine.validate(cases)

    # 保存校验结果
    result_path = TEST_CASES_DIR / f"{doc_name}_validation.json"
    result_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成 Markdown 报告
    lines = [
        f"# 测试用例规则校验报告\n",
        f"**文档**: {doc_name}",
        f"**用例总数**: {result.total_cases}",
        f"**通过**: {result.passed} ({result.pass_rate:.1%})",
        f"**违规**: {len(result.violations)} 项\n",
        f"| 级别 | 数量 |",
        f"|------|------|",
        f"| 🔴 Error | {result.summary.get('error', 0)} |",
        f"| 🟡 Warning | {result.summary.get('warning', 0)} |",
        f"| 🔵 Info | {result.summary.get('info', 0)} |\n",
    ]

    if result.violations:
        lines.append("## 违规详情\n")
        lines.append("| 用例ID | 规则 | 级别 | 问题 | 建议 |")
        lines.append("|--------|------|------|------|------|")

        for v in result.violations[:50]:  # 最多显示 50 条
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(v.severity, "⚪")
            lines.append(
                f"| {v.case_id} | {v.rule_name} | {icon} | {v.message} | {v.suggestion} |"
            )

        if len(result.violations) > 50:
            lines.append(f"\n... 还有 {len(result.violations) - 50} 条违规未显示")
    else:
        lines.append("\n✅ 所有用例通过校验！\n")

    lines.append(f"\n📄 校验数据: {result_path}")

    return "\n".join(lines)


@mcp.tool(
    name="score_case_quality",
    description="对测试用例进行质量评分，从覆盖率、可执行性、准确性、完整性、优先级五个维度",
)
def score_case_quality(doc_name: str) -> str:
    """质量评分测试用例。

    Args:
        doc_name: 测试用例对应的文档名称

    Returns:
        质量评分报告
    """
    cases_path = TEST_CASES_DIR / f"{doc_name}_cases.json"
    if not cases_path.exists():
        return f"❌ 未找到测试用例: {cases_path}"

    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    scorer = QualityScorer()
    result = scorer.score(cases)

    # 保存评分结果
    result_path = TEST_CASES_DIR / f"{doc_name}_quality.json"
    result_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成 Markdown 报告
    grade_emoji = {"A+": "🌟", "A": "⭐", "B+": "👍", "B": "👌", "C": "⚠️", "D": "🔧", "F": "❌"}
    emoji = grade_emoji.get(result.grade, "❓")

    lines = [
        f"# 测试用例质量评分报告 {emoji}\n",
        f"**文档**: {doc_name}",
        f"**用例数**: {result.total_cases}",
        f"**总体评分**: {result.overall_score:.2f} / 5.0",
        f"**等级**: {result.grade}\n",
        "## 维度评分\n",
        "| 维度 | 得分 | 权重 | 评价 |",
        "|------|------|------|------|",
    ]

    for d in result.dimension_scores:
        bar = "█" * int(d.score) + "░" * (5 - int(d.score))
        lines.append(f"| {d.dimension} | {d.score:.2f} {bar} | {d.weight:.0%} | {d.details[0] if d.details else ''} |")

    lines.append("\n## 改进建议\n")
    for suggestion in result.suggestions:
        lines.append(f"- {suggestion}")

    lines.append(f"\n📄 评分数据: {result_path}")

    return "\n".join(lines)


# ====== RESOURCES ======

@mcp.resource(
    uri="test-case-library://",
    name="test-case-library",
    description="测试用例库，包含所有已生成的测试用例",
    mime_type="application/json",
)
def get_test_case_library() -> str:
    """获取完整测试用例库。"""
    all_cases = []
    for f in TEST_CASES_DIR.glob("*_cases.json"):
        try:
            cases = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(cases, list):
                all_cases.extend(cases)
        except (json.JSONDecodeError, OSError) as e:
            # 跳过损坏或不可读的文件
            continue
    return json.dumps(all_cases, ensure_ascii=False, indent=2)


@mcp.resource(
    uri="requirement-doc://{doc_name}",
    name="requirement-doc",
    description="已解析的需求文档（Markdown 格式）",
    mime_type="text/markdown",
)
def get_requirement_doc(doc_name: str) -> str:
    """获取指定需求文档的解析内容。

    Args:
        doc_name: 文档名称（不含后缀）
    """
    path = PARSED_DIR / f"{doc_name}.md"
    if not path.exists():
        return f"❌ 文档不存在: {doc_name}"
    return path.read_text(encoding="utf-8")


@mcp.resource(
    uri="requirement-modules://{doc_name}",
    name="requirement-modules",
    description="拆分后的子需求模块索引",
    mime_type="application/json",
)
def get_requirement_modules(doc_name: str) -> str:
    """获取拆分后的子需求模块列表。

    Args:
        doc_name: 文档名称
    """
    index_path = PARSED_DIR / "split" / doc_name / f"{doc_name}_index.json"
    if not index_path.exists():
        return json.dumps({"error": "未找到拆分结果", "doc_name": doc_name}, ensure_ascii=False)
    return index_path.read_text(encoding="utf-8")


# ====== PROMPTS ======

@mcp.prompt(
    name="analyze-requirement",
    description="资深测试专家级需求分析，运用多维度分析法提取功能点、边界条件、风险点和测试策略",
)
def analyze_requirement_prompt() -> str:
    """资深测试专家级需求分析提示词。"""
    return """# 角色定位

你是一名拥有15年以上软件测试经验的资深测试专家，精通黑盒测试、白盒测试、灰盒测试各类测试模式。你仅聚焦功能测试范畴。

# 多维度需求分析框架

请对以下需求文档进行系统化分析，严格按照以下五个维度展开：

## 一、功能性分析

1. **核心业务流程**：识别主业务流的关键功能节点
2. **辅助配套功能**：梳理支撑核心业务运行的辅助功能
3. **潜在隐性需求**：挖掘需求文档未显式描述但业务逻辑隐含的功能点
4. **前置后置条件**：梳理功能执行的前置条件、后置结果、数据依赖关系

## 二、非功能性分析（功能测试视角）

1. **易用性**：界面交互合理性、操作引导完整性、错误提示友好性
2. **兼容性**：不同数据格式/浏览器/设备的兼容表现
3. **系统容错性**：异常输入/异常操作下的系统处理机制
4. **运行稳定性**：重复操作/长时间运行下的功能稳定性

## 三、约束条件分析

1. **业务校验规则**：字段格式/长度/范围/唯一性等业务规则
2. **技术架构限制**：接口限制/数据类型限制/并发限制
3. **部署环境约束**：不同环境下的功能表现差异

## 四、风险点识别

1. **复杂逻辑模块**：多条件组合/嵌套判断/状态流转复杂的区域
2. **边界操作场景**：数值边界/长度边界/时间边界/空值边界
3. **用户误操作行为**：非正常顺序操作/重复提交/快速连续点击
4. **系统薄弱易缺陷区域**：历史缺陷高发区/代码复杂度高的模块

## 五、测试策略建议

对每个功能模块，建议最适合的测试设计方法组合：
- 等价类划分法 + 边界值分析法（用于输入验证类功能）
- 决策表法（用于多条件组合类功能）
- 状态转换法（用于有明确状态流转的功能）
- 场景法（用于业务流程类功能）
- 正交试验法（用于多因素交叉类功能）
- 错误推测法（用于高风险/历史缺陷多发模块）

# 输出格式

```
# 需求分析报告

## 模块: [模块名称]

### 功能点清单
| 序号 | 功能点 | 类型(核心/辅助/隐性) | 前置条件 | 后置结果 | 风险等级 |

### 边界条件
| 功能点 | 边界类型 | 边界值 | 临界邻近值 |

### 约束规则
| 规则类型 | 规则描述 | 影响范围 |

### 风险点
| 风险描述 | 风险等级(高/中/低) | 建议测试方法 | 建议优先级 |

### 测试策略
- 推荐测试方法组合: [方法列表]
- 覆盖率目标: 需求100% / 边界100% / 异常≥90%
- 重点测试区域: [高风险功能点]
```

请确保分析全面、系统、结构化，不遗漏任何隐含需求和边界场景。"""


@mcp.prompt(
    name="generate-boundary-cases",
    description="资深测试专家级边界值分析，运用系统化方法生成全面的边界和异常场景用例",
)
def generate_boundary_cases_prompt() -> str:
    """资深测试专家级边界值用例生成提示词。"""
    return """# 角色定位

你是一名拥有15年以上经验的资深测试专家，精通边界值分析法、等价类划分法、错误推测法等系统化测试设计技术。

# 边界值分析系统化方法

边界值分析法的核心原则：**故障往往出现在输入变量的边界值附近，而非取值范围内部**。

请对以下功能的每个输入项，严格按照以下边界类型生成测试用例：

## 一、数值类型边界

| 边界类型 | 说明 | 示例 |
|---------|------|------|
| 最小值 | 允许的最小数值 | 0, 1, -999999 |
| 最小值+1 | 略高于最小值 | 1, 2 |
| 正常值 | 范围内的典型值 | 50, 100 |
| 最大值-1 | 略低于最大值 | 98, 999 |
| 最大值 | 允许的最大数值 | 99, 1000 |
| 最大值+1 | 超出最大值 | 100, 1001 |
| 零值 | 特殊数值0 | 0 |
| 负值 | 负数输入 | -1, -100 |

## 二、字符串类型边界

| 边界类型 | 说明 | 示例 |
|---------|------|------|
| 空字符串 | 长度为0 | "" |
| 最小长度 | 允许的最短长度 | 1个字符 |
| 最小长度+1 | 略长于最短 | 2个字符 |
| 正常长度 | 典型长度 | 10个字符 |
| 最大长度-1 | 略短于最长 | 限制-1 |
| 最大长度 | 允许的最长长度 | 限制值 |
| 最大长度+1 | 超出长度限制 | 限制+1 |
| 特殊字符 | 换行/制表/Unicode | \\n, \\t, emoji |
| 空白字符 | 全空格/首尾空格 | "   " |
| SQL注入 | 注入攻击字符串 | ' OR '1'='1 |
| XSS攻击 | 跨站脚本 | <script>alert(1)</script> |

## 三、数组/集合类型边界

| 边界类型 | 说明 |
|---------|------|
| 空数组 | 0个元素 |
| 1个元素 | 最小非空 |
| 最大容量 | 允许的最大元素数 |
| 最大容量+1 | 超出容量限制 |
| 重复元素 | 含重复值的数组 |

## 四、时间类型边界

| 边界类型 | 说明 | 示例 |
|---------|------|------|
| 时间起点 | 最小时间值 | 1970-01-01 |
| 时间终点 | 最大时间值 | 9999-12-31 |
| 闰年2月29日 | 特殊日期 | 2024-02-29 |
| 跨天边界 | 23:59:59 → 00:00:00 | 午夜时分 |
| 时区切换 | 夏令时切换点 | 02:00:00 |

## 五、错误推测法补充

结合历史缺陷模式和用户误操作习惯，补充以下场景：
- 快速连续点击提交按钮（重复提交）
- 操作过程中网络中断
- 操作过程中浏览器返回/刷新
- 超长路径/嵌套层级
- 并发修改同一数据
- 权限越权操作

# 输出格式

```json
{
  "function_name": "功能名称",
  "input_fields": [
    {
      "field_name": "字段名",
      "field_type": "数值|字符串|数组|时间",
      "constraints": "约束描述",
      "boundary_cases": [
        {
          "test_data": "测试数据值",
          "boundary_type": "最小值|最大值|空值|超长|特殊字符|...",
          "expected_result": "系统预期行为（必须包含具体的页面表现/提示信息/状态变化）",
          "priority": "P0|P1|P2|P3",
          "test_method": "边界值|等价类|错误推测"
        }
      ]
    }
  ]
}
```

# 约束

- 仅生成功能测试相关的边界用例，不生成性能测试、安全测试用例
- 每个边界点必须标注使用的测试设计方法
- 预期结果必须具体可验证（包含可观察的系统行为描述）
- 必须覆盖正常合规数据、边界临界数据、异常违规数据、特殊格式数据四类
- 必须考虑常规顺序操作、重复操作、逆向操作、随机顺序操作四种操作行为"""


@mcp.prompt(
    name="review-case-quality",
    description="Review 测试用例质量，检查覆盖率、可执行性和准确性",
)
def review_case_quality_prompt() -> str:
    """用例质量 Review 提示词。"""
    return """你是一名测试质量评审专家。请对以下测试用例进行质量 Review，从以下维度评分（1-5分）：

1. **覆盖率**：是否覆盖了所有功能点和边界条件
2. **可执行性**：步骤是否具体、预期结果是否可验证
3. **准确性**：是否符合需求描述，无歧义
4. **优先级合理性**：P0/P1/P2/P3 分配是否合理
5. **完整性**：前置条件、测试数据是否明确

输出格式：
```
## 评审报告

### 总体评分: [X]/5

### 问题清单
| 用例ID | 问题 | 严重程度 | 建议 |

### 优秀用例
| 用例ID | 亮点 |

### 改进建议
[具体建议]
```"""


# ====== CLI Entry ======

def main():
    """MCP Server 入口。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
