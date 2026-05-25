"""需求文档拆分器 - 将大需求文档按模块拆分为独立小需求."""

from pathlib import Path
import json
import re
from dataclasses import dataclass, asdict


@dataclass
class SubRequirement:
    """拆分后的子需求单元."""

    id: str
    title: str
    module: str
    content: str
    source_range: str
    priority: str = "normal"
    dependencies: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class RequirementSplitter:
    """将 Markdown 格式的需求文档拆分为多个模块化的子需求."""

    def __init__(self):
        self.modules: list[SubRequirement] = []

    def split(self, markdown_text: str, doc_name: str = "doc") -> list[SubRequirement]:
        """解析 Markdown 文本，按标题层级拆分为子需求.

        拆分策略：
        - 一级/二级标题作为模块边界
        - 三级及以下作为子需求
        - 保留每个子需求的完整上下文和溯源信息

        Args:
            markdown_text: 解析后的 Markdown 文本
            doc_name: 文档名称，用于生成 ID

        Returns:
            SubRequirement 列表
        """
        self.modules = []
        lines = markdown_text.split("\n")

        current_module = "未分类"
        current_section = ""
        buffer: list[str] = []
        section_counter = 0

        for line in lines:
            stripped = line.strip()

            # 检测一级/二级标题 → 模块边界
            if stripped.startswith("# ") and not stripped.startswith("## "):
                # 保存之前的缓冲内容
                if buffer:
                    self._save_module(
                        doc_name, section_counter, current_module, current_section, buffer
                    )
                    section_counter += 1

                current_module = stripped.lstrip("# ").strip()
                current_section = ""
                buffer = [line]

            # 检测三级标题 → 子需求边界
            elif stripped.startswith("### "):
                if buffer:
                    self._save_module(
                        doc_name, section_counter, current_module, current_section, buffer
                    )
                    section_counter += 1

                current_section = stripped.lstrip("# ").strip()
                buffer = [line]

            else:
                buffer.append(line)

        # 保存最后一个模块
        if buffer:
            self._save_module(
                doc_name, section_counter, current_module, current_section, buffer
            )

        return self.modules

    def _save_module(
        self,
        doc_name: str,
        idx: int,
        module: str,
        section: str,
        buffer: list[str],
    ) -> None:
        """保存一个子需求单元."""
        content = "\n".join(buffer).strip()
        if not content or len(content) < 30:
            return

        # 生成 ID
        module_slug = re.sub(r"[^\w一-鿿]", "_", module)[:20]
        req_id = f"{doc_name}_{module_slug}_{idx:03d}"

        # 尝试提取优先级
        priority = self._extract_priority(content)

        # 尝试提取依赖关系
        dependencies = self._extract_dependencies(content)

        sub_req = SubRequirement(
            id=req_id,
            title=section or module,
            module=module,
            content=content,
            source_range=f"{module} > {section}" if section else module,
            priority=priority,
            dependencies=dependencies,
        )
        self.modules.append(sub_req)

    def _extract_priority(self, content: str) -> str:
        """从内容中提取优先级标记."""
        priority_patterns = [
            (r"优先级[：:]\s*(P0|P1|P2|P3)", 1),
            (r"priority[：:]\s*(high|medium|low)", 1),
            (r"【(高|中|低)优先级】", 1),
        ]
        for pattern, group in priority_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(group).upper()
        return "normal"

    def _extract_dependencies(self, content: str) -> list[str] | None:
        """从内容中提取依赖关系."""
        dep_patterns = [
            r"依赖[：:]\s*([\w\-_，,]+)",
            r"depends on[：:]\s*([\w\-_，,]+)",
        ]
        for pattern in dep_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                deps = re.split(r"[,，]", match.group(1))
                return [d.strip() for d in deps if d.strip()]
        return None

    def export_to_files(self, output_dir: str | Path, doc_name: str = "doc") -> list[Path]:
        """将拆分的子需求导出为独立 Markdown 文件.

        Args:
            output_dir: 输出目录
            doc_name: 文档名称前缀

        Returns:
            生成的文件路径列表
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for req in self.modules:
            filename = f"{doc_name}_{req.id}.md"
            filepath = output_dir / filename

            header = f"""---
id: {req.id}
module: {req.module}
title: {req.title}
source: {req.source_range}
priority: {req.priority}
dependencies: {json.dumps(req.dependencies or [], ensure_ascii=False)}
---

"""
            filepath.write_text(header + req.content, encoding="utf-8")
            paths.append(filepath)

        # 同时生成索引文件
        index_path = output_dir / f"{doc_name}_index.json"
        index_data = {
            "doc_name": doc_name,
            "total_modules": len(self.modules),
            "modules": [req.to_dict() for req in self.modules],
        }
        index_path.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return paths

    def get_module_summary(self) -> str:
        """获取模块拆分摘要报告."""
        lines = [
            "# 需求文档拆分报告\n",
            f"共拆分为 **{len(self.modules)}** 个模块\n",
            "\n## 模块清单\n",
            "| ID | 模块 | 子需求 | 优先级 | 依赖 |",
            "|----|------|--------|--------|------|",
        ]
        for req in self.modules:
            deps = ", ".join(req.dependencies) if req.dependencies else "-"
            lines.append(
                f"| {req.id} | {req.module} | {req.title} | {req.priority} | {deps} |"
            )
        return "\n".join(lines)
