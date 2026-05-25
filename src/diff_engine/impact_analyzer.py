"""用例影响范围分析器.

根据文档差异检测结果，定位受影响的测试用例，
分析影响类型并给出同步建议.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .doc_differ import ChangeType, DiffResult, SectionDiff


class ImpactType(Enum):
    """影响类型."""

    NEW_REQUIREMENT = "new_requirement"      # 新增需求 → 新增用例
    LOGIC_CHANGED = "logic_changed"          # 功能逻辑修改 → 用例需 review
    REQUIREMENT_REMOVED = "requirement_removed"  # 需求删除 → 用例废弃
    DEPENDENCY_CHANGED = "dependency_changed"    # 依赖变更 → 关联用例需 review
    NO_IMPACT = "no_impact"                  # 无影响


@dataclass
class CaseImpact:
    """单个用例的影响分析."""

    case_id: str
    case_title: str
    impact_type: ImpactType
    source_section: str
    reason: str
    suggested_action: str  # add / review / deprecate / none
    priority: str = "normal"  # high / normal / low


@dataclass
class ImpactResult:
    """影响分析结果."""

    doc_name: str
    risk_level: str
    impacts: list[CaseImpact] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "doc_name": self.doc_name,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "impacts": [
                {
                    "case_id": i.case_id,
                    "case_title": i.case_title,
                    "impact_type": i.impact_type.value,
                    "source_section": i.source_section,
                    "reason": i.reason,
                    "suggested_action": i.suggested_action,
                    "priority": i.priority,
                }
                for i in self.impacts
            ],
        }


class ImpactAnalyzer:
    """用例影响范围分析器."""

    def __init__(self, cases_dir: str | Path | None = None):
        """
        Args:
            cases_dir: 测试用例 JSON 文件存放目录
        """
        self.cases_dir = Path(cases_dir) if cases_dir else None

    def analyze(self, diff: DiffResult, existing_cases: list[dict]) -> ImpactResult:
        """分析文档变更对现有用例的影响.

        Args:
            diff: 文档差异结果
            existing_cases: 现有测试用例列表

        Returns:
            ImpactResult 影响分析结果
        """
        result = ImpactResult(doc_name=diff.doc_name, risk_level=diff.risk_level)

        # 建立用例到章节的映射
        case_map: dict[str, list[dict]] = {}
        for case in existing_cases:
            source = case.get("source", "")
            case_map.setdefault(source, []).append(case)

        for change in diff.changes:
            impacts = self._analyze_change(change, case_map)
            result.impacts.extend(impacts)

        # 计算摘要
        result.summary = self._compute_summary(result.impacts)
        return result

    def analyze_from_files(
        self,
        diff: DiffResult,
        cases_path: str | Path,
    ) -> ImpactResult:
        """从文件加载用例进行分析.

        Args:
            diff: 文档差异结果
            cases_path: 用例 JSON 文件路径
        """
        cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
        return self.analyze(diff, cases)

    def _analyze_change(
        self,
        change: SectionDiff,
        case_map: dict[str, list[dict]],
    ) -> list[CaseImpact]:
        """分析单个变更的影响."""
        impacts: list[CaseImpact] = []
        section_key = change.title

        if change.change_type == ChangeType.ADDED:
            # 新增章节 → 需要新增用例
            impacts.append(
                CaseImpact(
                    case_id="NEW",
                    case_title=f"新增用例: {change.title}",
                    impact_type=ImpactType.NEW_REQUIREMENT,
                    source_section=section_key,
                    reason=f"新增需求章节: {change.title}",
                    suggested_action="add",
                    priority="high",
                )
            )

        elif change.change_type == ChangeType.REMOVED:
            # 删除章节 → 关联用例废弃
            affected = self._find_affected_cases(section_key, case_map)
            if affected:
                for case in affected:
                    impacts.append(
                        CaseImpact(
                            case_id=case.get("id", "UNKNOWN"),
                            case_title=case.get("title", ""),
                            impact_type=ImpactType.REQUIREMENT_REMOVED,
                            source_section=section_key,
                            reason=f"需求章节已删除: {change.title}",
                            suggested_action="deprecate",
                            priority="high",
                        )
                    )
            else:
                impacts.append(
                    CaseImpact(
                        case_id="N/A",
                        case_title="无关联用例",
                        impact_type=ImpactType.REQUIREMENT_REMOVED,
                        source_section=section_key,
                        reason=f"需求章节已删除（无关联用例）: {change.title}",
                        suggested_action="none",
                        priority="low",
                    )
                )

        elif change.change_type == ChangeType.MODIFIED:
            # 修改章节 → 关联用例需要 review
            affected = self._find_affected_cases(section_key, case_map)
            if affected:
                for case in affected:
                    impacts.append(
                        CaseImpact(
                            case_id=case.get("id", "UNKNOWN"),
                            case_title=case.get("title", ""),
                            impact_type=ImpactType.LOGIC_CHANGED,
                            source_section=section_key,
                            reason=f"需求章节已修改 ({change.similarity:.0%} 相似): {change.title}",
                            suggested_action="review",
                            priority="high" if change.similarity < 0.5 else "normal",
                        )
                    )

                # 检测是否有新增内容需要补充用例
                if change.details:
                    for detail in change.details:
                        if detail.get("type") == "lines_added" and detail.get("count", 0) > 5:
                            impacts.append(
                                CaseImpact(
                                    case_id="NEW",
                                    case_title=f"补充用例: {change.title}",
                                    impact_type=ImpactType.NEW_REQUIREMENT,
                                    source_section=section_key,
                                    reason=f"章节新增大量内容，可能需要补充用例",
                                    suggested_action="add",
                                    priority="normal",
                                )
                            )
                            break
            else:
                # 修改了但没有关联用例 → 新增用例
                impacts.append(
                    CaseImpact(
                        case_id="NEW",
                        case_title=f"新增用例: {change.title}",
                        impact_type=ImpactType.NEW_REQUIREMENT,
                        source_section=section_key,
                        reason=f"修改了章节但无现有用例覆盖: {change.title}",
                        suggested_action="add",
                        priority="normal",
                    )
                )

        return impacts

    def _find_affected_cases(
        self,
        section_key: str,
        case_map: dict[str, list[dict]],
    ) -> list[dict]:
        """查找受影响的用例.

        通过 source 字段匹配，支持模糊匹配.
        """
        results: list[dict] = []

        # 精确匹配
        if section_key in case_map:
            results.extend(case_map[section_key])

        # 模糊匹配：source 包含章节标题关键词
        keywords = self._extract_keywords(section_key)
        for source, cases in case_map.items():
            if source == section_key:
                continue
            source_keywords = self._extract_keywords(source)
            # 有共同关键词
            if keywords & source_keywords:
                for case in cases:
                    if case not in results:
                        results.append(case)

        return results

    def _extract_keywords(self, text: str) -> set[str]:
        """提取关键词集合."""
        # 简单的中文/英文分词
        words = set()
        # 英文单词
        import re
        words.update(w.lower() for w in re.findall(r"[a-zA-Z]+", text) if len(w) > 2)
        # 中文字（取 2-4 字词组）
        chars = re.findall(r"[一-鿿]", text)
        for i in range(len(chars)):
            for j in range(2, min(5, len(chars) - i + 1)):
                words.add("".join(chars[i : i + j]))
        return words

    def _compute_summary(self, impacts: list[CaseImpact]) -> dict[str, int]:
        """计算影响摘要."""
        summary: dict[str, int] = {
            "total": len(impacts),
            "add": 0,
            "review": 0,
            "deprecate": 0,
            "none": 0,
        }
        for i in impacts:
            if i.suggested_action in summary:
                summary[i.suggested_action] += 1
        return summary

    def generate_sync_plan(self, result: ImpactResult) -> dict[str, Any]:
        """生成同步执行计划.

        Returns:
            可执行的同步计划
        """
        plan: dict[str, Any] = {
            "doc_name": result.doc_name,
            "risk_level": result.risk_level,
            "actions": [],
        }

        for impact in result.impacts:
            if impact.suggested_action == "add":
                plan["actions"].append({
                    "type": "generate",
                    "target": impact.source_section,
                    "reason": impact.reason,
                })
            elif impact.suggested_action == "review":
                plan["actions"].append({
                    "type": "review",
                    "case_id": impact.case_id,
                    "reason": impact.reason,
                })
            elif impact.suggested_action == "deprecate":
                plan["actions"].append({
                    "type": "deprecate",
                    "case_id": impact.case_id,
                    "reason": impact.reason,
                })

        return plan
