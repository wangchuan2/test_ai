"""测试用例生成引擎."""

import json
import re
from pathlib import Path
from typing import Any

from .llm_client import ClaudeClient


class TestCaseGenerator:
    """基于需求文档生成结构化测试用例."""

    def __init__(self, client: ClaudeClient | None = None):
        self.client = client

    def generate(
        self,
        requirement_text: str,
        historical_cases: list[dict] | None = None,
        doc_version: str = "1.0",
    ) -> list[dict[str, Any]]:
        """生成测试用例.

        Args:
            requirement_text: 结构化需求文本（Markdown）
            historical_cases: 历史用例列表，用于风格一致性
            doc_version: 需求文档版本号

        Returns:
            测试用例字典列表
        """
        if not self.client:
            raise ValueError("ClaudeClient is required")

        # 加载提示词模板
        system_prompt = self._load_prompt("testcase_generation")

        # 构建用户消息
        user_content = f"""请根据以下需求文档生成测试用例。

## 需求文档

{requirement_text}

"""

        if historical_cases:
            user_content += f"""## 参考历史用例风格

{json.dumps(historical_cases[:5], ensure_ascii=False, indent=2)}

请保持与上述历史用例类似的风格和详细程度。
"""

        user_content += f"""
## 文档版本
{doc_version}

请严格按照系统提示词中的 JSON 格式输出测试用例数组。
"""

        messages = [{"role": "user", "content": user_content}]

        response = self.client.chat(
            messages=messages,
            system=system_prompt,
            max_tokens=8192,
            temperature=0.2,
        )

        return self._parse_cases(response, doc_version)

    def generate_batch(
        self,
        requirements: list[tuple[str, str]],
        historical_cases: list[dict] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """批量生成多个模块的测试用例.

        Args:
            requirements: [(module_name, requirement_text), ...]
            historical_cases: 历史用例

        Returns:
            {module_name: [cases, ...]}
        """
        results: dict[str, list[dict[str, Any]]] = {}
        for module_name, req_text in requirements:
            results[module_name] = self.generate(req_text, historical_cases)
        return results

    def _load_prompt(self, name: str) -> str:
        """加载提示词模板."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / f"{name}.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

        # 默认提示词
        return self._default_generation_prompt()

    def _default_generation_prompt(self) -> str:
        """资深测试专家级用例生成系统提示词."""
        return """# 角色定位

你是一名拥有15年以上软件测试经验的资深测试专家，精通黑盒测试、白盒测试、灰盒测试各类测试模式。你仅聚焦功能测试范畴，不考量性能、安全相关测试内容。

你熟练运用以下七大系统化测试设计技术：
1. 等价类划分法 — 区分有效等价类（合规数据）与无效等价类（空值/错误类型/超限数据/特殊字符）
2. 边界值分析法 — 核验数值/字符串/数组/时间等类型的边界临界点及临界邻近数值
3. 决策表法 — 汇总全部输入条件，组合条件取值，覆盖正常业务、异常报错、边界极限三类规则
4. 状态转换法 — 区分初始/中间/结束/异常四类状态，校验所有状态流转路径
5. 正交试验法 — 提取业务关键影响因子，合理精简组合数量，高效完成多条件交叉测试
6. 场景法 — 搭建标准主流程、异常分支、边界极限、常规操作等各类测试场景
7. 错误推测法 — 结合历史缺陷、业务风险、用户操作习惯，预判问题并设计异常测试用例

# 标准化测试设计流程

1. 需求分析：功能性分析（核心流程/辅助功能/隐性需求/前置后置条件）、非功能性分析（易用性/兼容性/容错性/稳定性）、约束条件分析（业务规则/技术限制/部署环境）、风险点识别（复杂逻辑/边界场景/误操作/薄弱区域）
2. 测试策略制定：根据风险等级确定测试重点
3. 用例设计：运用七大方法系统化设计
4. 覆盖率核验：需求覆盖率100%、边界覆盖率100%、业务规则覆盖率100%、功能覆盖率≥95%、异常覆盖率≥90%
5. 优化完善：去重、合并、精简
6. 最终定稿输出

# 高覆盖率保障标准

- 需求覆盖率 100%
- 边界覆盖率 100%
- 业务规则覆盖率 100%
- 功能覆盖率 ≥95%
- 异常覆盖率 ≥90%

# 测试数据必须覆盖

- 正常合规数据
- 边界临界数据
- 异常违规数据
- 特殊格式数据

# 操作行为必须覆盖

- 常规顺序操作
- 重复操作
- 逆向操作
- 随机顺序操作

# 输出格式

请输出 JSON 数组，每个元素是一个测试用例对象：

```json
[
  {
    "id": "TC-001",
    "module": "模块名称",
    "title": "用例标题，清晰描述测试场景",
    "precondition": "前置条件（含数据依赖关系）",
    "steps": ["步骤1", "步骤2", "步骤3"],
    "expected": "预期结果，必须可验证",
    "priority": "P0|P1|P2|P3",
    "type": "功能测试|兼容性测试|易用性测试|容错性测试",
    "source": "需求来源，如文档版本和章节",
    "test_method": "等价类|边界值|决策表|状态转换|正交试验|场景法|错误推测"
  }
]
```

# 优先级定义

- P0: 核心业务流程、阻塞性缺陷、高风险区域 — 必须100%覆盖
- P1: 重要功能节点、常见用户场景 — 必须覆盖
- P2: 辅助功能、一般操作场景 — 选择性覆盖
- P3: 边缘场景、低频操作、异常恢复 — 抽样覆盖

# 设计原则

1. **模块化设计**：按功能模块组织用例，结构清晰，支持长期维护
2. **场景全覆盖**：每个功能点必须覆盖正常流程、异常分支、边界极限
3. **数据驱动**：明确测试数据类型（正常/边界/异常/特殊）
4. **可验证性**：预期结果必须包含可观察的系统行为（页面跳转/提示信息/状态变化/数据变化）
5. **可执行性**：步骤具体到操作对象和操作动作（点击XX按钮/输入XX值/选择XX选项）
6. **异常场景**：每个功能至少包含2个异常流程用例（无效输入/越权操作/断网/超时）
7. **隐性需求**：挖掘需求文档未显式描述但业务逻辑隐含的场景
8. **预留空间**：覆盖突发情况与非常规测试场景

# 约束

- 仅生成功能测试相关用例，不生成性能测试、安全测试用例
- 用例标题必须以动词开头（验证/检查/确认/测试/确保）
- 每个用例必须标注使用的测试设计方法（test_method字段）
- 必须覆盖边界值和异常场景

请只输出 JSON 数组，不要输出任何其他解释文字。
"""

    def _parse_cases(self, response: str, doc_version: str) -> list[dict[str, Any]]:
        """解析 LLM 返回的 JSON 用例."""
        # 尝试提取 JSON 块
        json_match = re.search(r"```json\s*(\[.*?\])\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response.strip()
            if not json_str.startswith("["):
                # 尝试找到数组开始位置
                start = json_str.find("[")
                end = json_str.rfind("]")
                if start != -1 and end != -1:
                    json_str = json_str[start : end + 1]

        try:
            cases = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {response[:500]}")

        # 补充元数据
        for i, case in enumerate(cases):
            if "id" not in case:
                case["id"] = f"TC-{i+1:03d}"
            case["status"] = "draft"
            case["doc_version"] = doc_version
            case["review_status"] = "pending"

        return cases
