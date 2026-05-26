"""规则校验引擎.

预定义多种业务规则，对测试用例进行自动校验，
输出违规列表和修复建议.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class RuleSeverity(Enum):
    """规则严重级别."""

    ERROR = "error"       # 必须修复
    WARNING = "warning"   # 建议修复
    INFO = "info"         # 提示信息


@dataclass
class Rule:
    """单条校验规则."""

    id: str
    name: str
    description: str
    severity: RuleSeverity
    check: Callable[[dict], tuple[bool, str | None]]


@dataclass
class Violation:
    """违规项."""

    rule_id: str
    rule_name: str
    severity: str
    case_id: str
    case_title: str
    message: str
    suggestion: str


@dataclass
class ValidationResult:
    """校验结果."""

    total_cases: int = 0
    passed: int = 0
    violations: list[Violation] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed / self.total_cases

    def to_dict(self) -> dict:
        return {
            "total_cases": self.total_cases,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 3),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_name": v.rule_name,
                    "severity": v.severity,
                    "case_id": v.case_id,
                    "case_title": v.case_title,
                    "message": v.message,
                    "suggestion": v.suggestion,
                }
                for v in self.violations
            ],
            "summary": self.summary,
        }


class RuleEngine:
    """规则校验引擎."""

    # 内置规则
    BUILT_IN_RULES: list[Rule] = []

    def __init__(self, custom_rules: list[Rule] | None = None):
        self.rules = self._build_builtin_rules()
        if custom_rules:
            self.rules.extend(custom_rules)

    def validate(self, cases: list[dict]) -> ValidationResult:
        """校验测试用例列表.

        Args:
            cases: 测试用例字典列表

        Returns:
            ValidationResult 校验结果
        """
        result = ValidationResult(total_cases=len(cases))
        severity_count: dict[str, int] = {"error": 0, "warning": 0, "info": 0}

        for case in cases:
            case_passed = True
            for rule in self.rules:
                ok, message = rule.check(case)
                if not ok:
                    case_passed = False
                    violation = Violation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity.value,
                        case_id=case.get("id", "UNKNOWN"),
                        case_title=case.get("title", ""),
                        message=message or "未通过校验",
                        suggestion=self._get_suggestion(rule.id),
                    )
                    result.violations.append(violation)
                    severity_count[rule.severity.value] += 1

            if case_passed:
                result.passed += 1

        result.summary = severity_count
        return result

    def validate_single(self, case: dict) -> list[Violation]:
        """校验单个用例.

        Args:
            case: 单个测试用例

        Returns:
            违规列表（空列表表示通过）
        """
        violations: list[Violation] = []
        for rule in self.rules:
            ok, message = rule.check(case)
            if not ok:
                violations.append(
                    Violation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity.value,
                        case_id=case.get("id", "UNKNOWN"),
                        case_title=case.get("title", ""),
                        message=message or "未通过校验",
                        suggestion=self._get_suggestion(rule.id),
                    )
                )
        return violations

    def add_rule(self, rule: Rule) -> None:
        """添加自定义规则."""
        self.rules.append(rule)

    def _build_builtin_rules(self) -> list[Rule]:
        """构建内置规则."""
        return [
            # === 字段存在性规则 ===
            Rule(
                id="R001",
                name="用例ID必填",
                description="每条用例必须有唯一的ID",
                severity=RuleSeverity.ERROR,
                check=lambda c: (
                    bool(isinstance(c.get("id"), (str, int)) and str(c.get("id")).strip()),
                    "用例ID不能为空",
                ),
            ),
            Rule(
                id="R002",
                name="用例标题必填",
                description="用例标题必须清晰描述测试场景",
                severity=RuleSeverity.ERROR,
                check=lambda c: (
                    bool(isinstance(c.get("title"), str) and len(c.get("title").strip()) >= 5),
                    "用例标题不能为空且长度不少于5个字符",
                ),
            ),
            Rule(
                id="R003",
                name="测试步骤必填",
                description="必须有具体的测试步骤",
                severity=RuleSeverity.ERROR,
                check=lambda c: (
                    bool(c.get("steps") and len(c.get("steps", [])) > 0),
                    "测试步骤不能为空",
                ),
            ),
            Rule(
                id="R004",
                name="预期结果必填",
                description="必须有明确的预期结果",
                severity=RuleSeverity.ERROR,
                check=lambda c: (
                    bool(c.get("expected") and len(str(c.get("expected")).strip()) > 0),
                    "预期结果不能为空",
                ),
            ),
            # === 内容模式规则 ===
            Rule(
                id="R005",
                name="用例标题格式",
                description="标题应以动词开头，描述清晰",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    bool(c.get("title") and str(c.get("title")).startswith((
                        "验证", "检查", "确认", "测试", "确保",
                        "Verify", "Check", "Confirm", "Test", "Ensure",
                    ))),
                    "标题建议以'验证/检查/确认/测试/Verify/Check'等动词开头",
                ),
            ),
            Rule(
                id="R006",
                name="步骤应具体可执行",
                description="测试步骤不能太笼统",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    all(len(str(s).strip()) >= 3 for s in c.get("steps", [])),
                    "测试步骤应具体（每条不少于3个字符）",
                ),
            ),
            Rule(
                id="R007",
                name="预期结果应可验证",
                description="预期结果必须包含可观察的验证点",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    any(kw in str(c.get("expected", "")).lower() for kw in [
                        "显示", "跳转", "提示", "返回", "成功", "失败",
                        "show", "redirect", "display", "return", "success", "error",
                    ]),
                    "预期结果应包含可验证的关键词（如显示/跳转/提示/成功等）",
                ),
            ),
            # === 业务规则 ===
            Rule(
                id="R008",
                name="优先级格式正确",
                description="优先级必须是 P0/P1/P2/P3 之一",
                severity=RuleSeverity.ERROR,
                check=lambda c: (
                    str(c.get("priority", "")).upper() in ("P0", "P1", "P2", "P3"),
                    "优先级必须是 P0/P1/P2/P3 之一",
                ),
            ),
            Rule(
                id="R009",
                name="用例类型有效",
                description="用例类型必须是预定义的有效类型",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    str(c.get("type", "")).lower() in [
                        "功能测试", "性能测试", "兼容性测试", "安全测试",
                        "ui测试", "接口测试", "回归测试", "冒烟测试",
                        "functional", "performance", "compatibility", "security",
                        "ui", "api", "regression", "smoke",
                    ],
                    "用例类型建议使用标准值（功能/性能/安全/UI/接口等）",
                ),
            ),
            Rule(
                id="R010",
                name="应有需求来源",
                description="用例应记录来源需求文档信息",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    bool(c.get("source") or c.get("doc_version")),
                    "建议记录用例来源（需求文档章节或版本）",
                ),
            ),
            # === 完整性规则 ===
            Rule(
                id="R011",
                name="前置条件建议填写",
                description="复杂用例应有前置条件说明",
                severity=RuleSeverity.INFO,
                check=lambda c: (
                    bool(c.get("precondition")),
                    "复杂用例建议填写前置条件",
                ),
            ),
            Rule(
                id="R012",
                name="应有模块归属",
                description="用例应归属到具体模块",
                severity=RuleSeverity.WARNING,
                check=lambda c: (
                    bool(c.get("module") and str(c.get("module")).strip()),
                    "建议为用例指定所属模块",
                ),
            ),
        ]

    def _get_suggestion(self, rule_id: str) -> str:
        """获取规则的修复建议."""
        suggestions = {
            "R001": "为用例分配唯一ID，如 TC-001",
            "R002": "补充用例标题，格式：验证[功能]在[条件]下的[行为]",
            "R003": "补充具体的测试操作步骤",
            "R004": "补充明确的预期结果，包含可观察的行为",
            "R005": "标题以动词开头，如'验证登录成功'",
            "R006": "步骤细化到具体操作，避免笼统描述",
            "R007": "预期结果包含'显示/跳转/提示'等可验证描述",
            "R008": "将优先级设为 P0(核心)/P1(重要)/P2(一般)/P3(边缘)",
            "R009": "使用标准用例类型名称",
            "R010": "记录用例对应的需求文档章节",
            "R011": "填写用例执行所需的前置环境和数据",
            "R012": "为用例指定所属功能模块",
        }
        return suggestions.get(rule_id, "请检查并修正")
