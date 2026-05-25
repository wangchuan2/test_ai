"""语义级文档差异检测引擎.

基于语义段落而非纯文本行进行 Diff，支持：
- 章节新增/删除/修改检测
- 表格结构变更对比
- 图片变更检测（基于哈希）
- 变更重要性评分
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChangeType(Enum):
    """变更类型."""

    ADDED = "added"           # 新增内容
    REMOVED = "removed"       # 删除内容
    MODIFIED = "modified"     # 内容修改
    UNCHANGED = "unchanged"   # 未变更
    TABLE_CHANGED = "table_changed"  # 表格结构变更
    IMAGE_CHANGED = "image_changed"  # 图片变更


@dataclass
class SectionDiff:
    """单个章节的差异."""

    change_type: ChangeType
    section_id: str
    title: str
    old_content: str = ""
    new_content: str = ""
    similarity: float = 0.0  # 0-1，用于 MODIFIED 类型
    details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DiffResult:
    """文档差异检测结果."""

    doc_name: str
    old_version: str = ""
    new_version: str = ""
    changes: list[SectionDiff] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    risk_level: str = "low"  # low / medium / high

    def to_dict(self) -> dict:
        return {
            "doc_name": self.doc_name,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "changes": [
                {
                    "change_type": c.change_type.value,
                    "section_id": c.section_id,
                    "title": c.title,
                    "similarity": round(c.similarity, 3),
                    "details": c.details,
                }
                for c in self.changes
            ],
        }


class DocumentDiffer:
    """语义级文档差异检测器."""

    def __init__(self, similarity_threshold: float = 0.7):
        """
        Args:
            similarity_threshold: 内容相似度阈值，低于此值视为修改
        """
        self.similarity_threshold = similarity_threshold

    def compare(self, old_text: str, new_text: str, doc_name: str = "doc") -> DiffResult:
        """比较两个版本的文档.

        Args:
            old_text: 旧版本 Markdown 文本
            new_text: 新版本 Markdown 文本
            doc_name: 文档名称

        Returns:
            DiffResult 差异结果
        """
        old_sections = self._extract_sections(old_text)
        new_sections = self._extract_sections(new_text)

        result = DiffResult(doc_name=doc_name)

        # 建立标题到内容的映射
        old_map = {s["id"]: s for s in old_sections}
        new_map = {s["id"]: s for s in new_sections}

        all_ids = set(old_map.keys()) | set(new_map.keys())

        for sid in sorted(all_ids):
            if sid not in old_map:
                # 新增章节
                section = new_map[sid]
                result.changes.append(
                    SectionDiff(
                        change_type=ChangeType.ADDED,
                        section_id=sid,
                        title=section["title"],
                        new_content=section["content"],
                        details=[{"reason": "新增章节"}],
                    )
                )
            elif sid not in new_map:
                # 删除章节
                section = old_map[sid]
                result.changes.append(
                    SectionDiff(
                        change_type=ChangeType.REMOVED,
                        section_id=sid,
                        title=section["title"],
                        old_content=section["content"],
                        details=[{"reason": "章节删除"}],
                    )
                )
            else:
                # 章节存在，检查内容是否变更
                old_sec = old_map[sid]
                new_sec = new_map[sid]
                similarity = self._compute_similarity(old_sec["content"], new_sec["content"])

                if similarity >= 0.99:
                    result.changes.append(
                        SectionDiff(
                            change_type=ChangeType.UNCHANGED,
                            section_id=sid,
                            title=old_sec["title"],
                            similarity=similarity,
                        )
                    )
                elif similarity >= self.similarity_threshold:
                    # 轻微修改
                    result.changes.append(
                        SectionDiff(
                            change_type=ChangeType.MODIFIED,
                            section_id=sid,
                            title=old_sec["title"],
                            old_content=old_sec["content"],
                            new_content=new_sec["content"],
                            similarity=similarity,
                            details=self._find_content_diff(
                                old_sec["content"], new_sec["content"]
                            ),
                        )
                    )
                else:
                    # 大幅修改或重写
                    result.changes.append(
                        SectionDiff(
                            change_type=ChangeType.MODIFIED,
                            section_id=sid,
                            title=old_sec["title"],
                            old_content=old_sec["content"],
                            new_content=new_sec["content"],
                            similarity=similarity,
                            details=[{"reason": "内容大幅修改", "similarity": round(similarity, 3)}],
                        )
                    )

        # 计算摘要
        result.summary = self._compute_summary(result.changes)
        result.risk_level = self._assess_risk(result.changes)

        return result

    def compare_files(self, old_path: str | Path, new_path: str | Path) -> DiffResult:
        """比较两个文件.

        Args:
            old_path: 旧版本文件路径
            new_path: 新版本文件路径
        """
        old_text = Path(old_path).read_text(encoding="utf-8")
        new_text = Path(new_path).read_text(encoding="utf-8")
        doc_name = Path(new_path).stem
        return self.compare(old_text, new_text, doc_name)

    def _extract_sections(self, text: str) -> list[dict]:
        """提取语义章节.

        按 #/##/### 标题拆分，保留表格、列表等结构信息.
        """
        lines = text.split("\n")
        sections: list[dict] = []
        current: dict | None = None
        buffer: list[str] = []
        counter = 0

        for line in lines:
            stripped = line.strip()

            # 检测标题行
            heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading_match:
                # 保存上一个章节
                if current and buffer:
                    current["content"] = "\n".join(buffer)
                    current["hash"] = self._hash(current["content"])
                    sections.append(current)

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                counter += 1
                current = {
                    "id": f"sec_{level}_{counter:04d}_{self._slug(title)}",
                    "level": level,
                    "title": title,
                    "content": "",
                    "hash": "",
                }
                buffer = [line]
            else:
                buffer.append(line)

        # 保存最后一个章节
        if current and buffer:
            current["content"] = "\n".join(buffer)
            current["hash"] = self._hash(current["content"])
            sections.append(current)

        return sections

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度 (0-1).

        使用字符级 Jaccard 相似度，兼顾效率和准确性.
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0

        # 分词：按字符 n-gram
        def ngrams(text: str, n: int = 3) -> set[str]:
            text = re.sub(r"\s+", "", text.lower())
            return {text[i : i + n] for i in range(len(text) - n + 1)} if len(text) >= n else {text}

        s1 = ngrams(text1)
        s2 = ngrams(text2)

        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        intersection = len(s1 & s2)
        union = len(s1 | s2)
        return intersection / union

    def _find_content_diff(self, old: str, new: str) -> list[dict]:
        """找出具体的差异点."""
        details: list[dict] = []

        # 检测表格变更
        old_tables = self._count_tables(old)
        new_tables = self._count_tables(new)
        if old_tables != new_tables:
            details.append({
                "type": "table_count_change",
                "old": old_tables,
                "new": new_tables,
            })

        # 检测图片变更
        old_images = self._count_images(old)
        new_images = self._count_images(new)
        if old_images != new_images:
            details.append({
                "type": "image_count_change",
                "old": old_images,
                "new": new_images,
            })

        # 检测关键行变化（用行级 diff）
        old_lines = set(old.splitlines())
        new_lines = set(new.splitlines())
        added_lines = new_lines - old_lines
        removed_lines = old_lines - new_lines

        if added_lines:
            details.append({
                "type": "lines_added",
                "count": len(added_lines),
                "examples": list(added_lines)[:3],
            })
        if removed_lines:
            details.append({
                "type": "lines_removed",
                "count": len(removed_lines),
                "examples": list(removed_lines)[:3],
            })

        return details

    def _compute_summary(self, changes: list[SectionDiff]) -> dict[str, int]:
        """计算变更统计摘要."""
        summary: dict[str, int] = {
            "total": len(changes),
            "added": 0,
            "removed": 0,
            "modified": 0,
            "unchanged": 0,
        }
        for c in changes:
            if c.change_type == ChangeType.ADDED:
                summary["added"] += 1
            elif c.change_type == ChangeType.REMOVED:
                summary["removed"] += 1
            elif c.change_type == ChangeType.MODIFIED:
                summary["modified"] += 1
            elif c.change_type == ChangeType.UNCHANGED:
                summary["unchanged"] += 1
        return summary

    def _assess_risk(self, changes: list[SectionDiff]) -> str:
        """评估变更风险等级."""
        modified = [c for c in changes if c.change_type == ChangeType.MODIFIED]
        added = [c for c in changes if c.change_type == ChangeType.ADDED]
        removed = [c for c in changes if c.change_type == ChangeType.REMOVED]

        # 有删除 = 高风险
        if removed:
            return "high"
        # 新增超过 3 个章节或修改超过 5 个章节 = 中风险
        if len(added) > 3 or len(modified) > 5:
            return "medium"
        # 少量修改 = 低风险
        return "low"

    def _hash(self, text: str) -> str:
        """计算文本哈希."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _slug(self, text: str) -> str:
        """将标题转换为 slug."""
        return re.sub(r"[^\w]", "_", text)[:30]

    def _count_tables(self, text: str) -> int:
        """统计表格数量."""
        return len(re.findall(r"^\|.*\|$", text, re.MULTILINE)) // 2

    def _count_images(self, text: str) -> int:
        """统计图片引用数量."""
        return len(re.findall(r"!\[.*?\]\(.*?\)", text)) + len(
            re.findall(r"\[Image \d+\]", text)
        )
