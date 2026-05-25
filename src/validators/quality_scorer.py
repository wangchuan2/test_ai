"""用例质量评分器.

从多个维度对测试用例进行质量评分，输出总体评分和改进建议.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ScoreDimension(Enum):
    """评分维度."""

    COVERAGE = "coverage"          # 覆盖率
    EXECUTABILITY = "executability"  # 可执行性
    ACCURACY = "accuracy"          # 准确性
    COMPLETENESS = "completeness"  # 完整性
    PRIORITY = "priority"          # 优先级合理性


@dataclass
class DimensionScore:
    """单个维度的评分."""

    dimension: str
    score: float  # 0-5
    weight: float
    details: list[str] = field(default_factory=list)


@dataclass
class QualityResult:
    """质量评分结果."""

    total_cases: int = 0
    overall_score: float = 0.0  # 0-5
    dimension_scores: list[DimensionScore] = field(default_factory=list)
    case_scores: dict[str, float] = field(default_factory=dict)  # case_id -> score
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_cases": self.total_cases,
            "overall_score": round(self.overall_score, 2),
            "grade": self.grade,
            "dimension_scores": [
                {
                    "dimension": d.dimension,
                    "score": round(d.score, 2),
                    "weight": d.weight,
                    "details": d.details,
                }
                for d in self.dimension_scores
            ],
            "case_scores": {k: round(v, 2) for k, v in self.case_scores.items()},
            "suggestions": self.suggestions,
        }

    @property
    def grade(self) -> str:
        """等级评定."""
        if self.overall_score >= 4.5:
            return "A+"
        elif self.overall_score >= 4.0:
            return "A"
        elif self.overall_score >= 3.5:
            return "B+"
        elif self.overall_score >= 3.0:
            return "B"
        elif self.overall_score >= 2.5:
            return "C"
        elif self.overall_score >= 2.0:
            return "D"
        else:
            return "F"


class QualityScorer:
    """用例质量评分器."""

    # 维度权重
    DEFAULT_WEIGHTS: dict[ScoreDimension, float] = {
        ScoreDimension.COVERAGE: 0.25,
        ScoreDimension.EXECUTABILITY: 0.25,
        ScoreDimension.ACCURACY: 0.20,
        ScoreDimension.COMPLETENESS: 0.20,
        ScoreDimension.PRIORITY: 0.10,
    }

    def __init__(self, weights: dict[ScoreDimension, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def score(self, cases: list[dict]) -> QualityResult:
        """对用例列表进行质量评分.

        Args:
            cases: 测试用例列表

        Returns:
            QualityResult 评分结果
        """
        result = QualityResult(total_cases=len(cases))

        if not cases:
            result.suggestions.append("无可用用例进行评分")
            return result

        # 各维度评分
        coverage = self._score_coverage(cases)
        executability = self._score_executability(cases)
        accuracy = self._score_accuracy(cases)
        completeness = self._score_completeness(cases)
        priority = self._score_priority(cases)

        result.dimension_scores = [coverage, executability, accuracy, completeness, priority]

        # 计算总分
        total_weight = sum(self.weights.values())
        result.overall_score = sum(
            d.score * self.weights[ScoreDimension(d.dimension)] / total_weight
            for d in result.dimension_scores
        )

        # 计算单个用例得分
        for case in cases:
            result.case_scores[case.get("id", "UNKNOWN")] = self._score_single_case(case)

        # 生成改进建议
        result.suggestions = self._generate_suggestions(result.dimension_scores)

        return result

    def score_single(self, case: dict) -> float:
        """评分单个用例.

        Args:
            case: 单个测试用例

        Returns:
            0-5 分
        """
        return self._score_single_case(case)

    def _score_coverage(self, cases: list[dict]) -> DimensionScore:
        """覆盖率评分.

        检查是否覆盖了不同维度（功能/性能/安全/UI/接口等）。
        """
        details: list[str] = []
        score = 5.0

        # 统计用例类型分布
        types: set[str] = set()
        for case in cases:
            t = str(case.get("type", "")).lower()
            types.add(t)

        # 类型多样性
        expected_types = {"功能测试", "性能测试", "安全测试", "ui测试", "接口测试"}
        covered = expected_types & types
        missing = expected_types - types

        if len(covered) < 2:
            score -= 2.0
            details.append(f"用例类型过于单一，仅覆盖 {len(covered)} 种类型")
        elif len(covered) < 4:
            score -= 1.0
            details.append(f"类型覆盖尚可，缺少: {', '.join(missing)}")
        else:
            details.append(f"类型覆盖良好，共 {len(covered)} 种")

        # 检查是否有异常场景
        has_negative = any(
            any(kw in str(case.get("title", "")).lower() for kw in
                ["异常", "错误", "失败", "无效", "越界", "为空", "不存在",
                 "error", "invalid", "fail", "null", "empty"])
            for case in cases
        )
        if not has_negative:
            score -= 1.0
            details.append("缺少异常/负面场景用例")
        else:
            details.append("包含异常场景用例")

        # 检查是否有边界值
        has_boundary = any(
            any(kw in str(case.get("title", "")).lower() for kw in
                ["边界", "最大", "最小", "上限", "下限", "最长", "最短",
                 "boundary", "max", "min", "limit"])
            for case in cases
        )
        if not has_boundary:
            score -= 1.0
            details.append("缺少边界值测试用例")
        else:
            details.append("包含边界值测试用例")

        return DimensionScore(
            dimension=ScoreDimension.COVERAGE.value,
            score=max(0, score),
            weight=self.weights[ScoreDimension.COVERAGE],
            details=details,
        )

    def _score_executability(self, cases: list[dict]) -> DimensionScore:
        """可执行性评分.

        检查步骤是否具体、预期结果是否可验证。
        """
        details: list[str] = []
        total_score = 0.0

        for case in cases:
            case_score = 5.0
            steps = case.get("steps", [])
            expected = str(case.get("expected", ""))

            # 步骤数量
            if len(steps) < 2:
                case_score -= 1.5

            # 步骤具体性（检查是否包含具体操作动词）
            action_verbs = ["点击", "输入", "选择", "上传", "提交", "打开", "关闭",
                           "click", "enter", "select", "upload", "submit", "open", "close"]
            has_action = any(
                any(v in str(step).lower() for v in action_verbs)
                for step in steps
            )
            if not has_action:
                case_score -= 1.0

            # 预期结果可验证性
            verifiable_keywords = ["显示", "跳转", "提示", "返回", "成功", "失败",
                                  "show", "redirect", "display", "return", "success", "error"]
            if not any(kw in expected.lower() for kw in verifiable_keywords):
                case_score -= 1.0

            # 预期结果长度
            if len(expected) < 10:
                case_score -= 0.5

            total_score += max(0, case_score)

        avg_score = total_score / len(cases) if cases else 0

        if avg_score >= 4.5:
            details.append("用例步骤清晰、预期结果可验证")
        elif avg_score >= 3.5:
            details.append("大部分用例可执行，部分需细化")
        else:
            details.append("较多用例步骤不够具体或预期结果模糊")

        return DimensionScore(
            dimension=ScoreDimension.EXECUTABILITY.value,
            score=avg_score,
            weight=self.weights[ScoreDimension.EXECUTABILITY],
            details=details,
        )

    def _score_accuracy(self, cases: list[dict]) -> DimensionScore:
        """准确性评分.

        检查用例是否符合需求描述，无歧义。
        """
        details: list[str] = []
        issues = 0

        for case in cases:
            title = str(case.get("title", ""))
            steps = case.get("steps", [])

            # 检查标题是否有歧义词汇
            ambiguous = ["可能", "大概", "也许", "若干", "一些",
                        "maybe", "perhaps", "some", "several"]
            if any(w in title.lower() for w in ambiguous):
                issues += 1

            # 检查步骤是否有循环引用或自相矛盾
            step_texts = [str(s).lower() for s in steps]
            for i, step in enumerate(step_texts):
                if "返回上一步" in step and i == 0:
                    issues += 1

        # 计算得分
        if issues == 0:
            score = 5.0
            details.append("用例描述准确，无歧义")
        elif issues <= len(cases) * 0.1:
            score = 4.0
            details.append(f"少量用例({issues}条)存在描述歧义")
        elif issues <= len(cases) * 0.3:
            score = 3.0
            details.append(f"部分用例({issues}条)描述不够准确")
        else:
            score = 2.0
            details.append(f"较多用例({issues}条)存在描述问题")

        return DimensionScore(
            dimension=ScoreDimension.ACCURACY.value,
            score=score,
            weight=self.weights[ScoreDimension.ACCURACY],
            details=details,
        )

    def _score_completeness(self, cases: list[dict]) -> DimensionScore:
        """完整性评分.

        检查前置条件、测试数据、清理步骤是否齐全。
        """
        details: list[str] = []

        has_precondition = sum(1 for c in cases if c.get("precondition"))
        has_module = sum(1 for c in cases if c.get("module"))
        has_source = sum(1 for c in cases if c.get("source"))

        total = len(cases)

        # 前置条件
        pre_rate = has_precondition / total if total else 0
        if pre_rate >= 0.8:
            details.append(f"前置条件填写率高 ({pre_rate:.0%})")
        elif pre_rate >= 0.5:
            details.append(f"前置条件填写率一般 ({pre_rate:.0%})")
        else:
            details.append(f"前置条件填写率较低 ({pre_rate:.0%})")

        # 模块归属
        mod_rate = has_module / total if total else 0
        if mod_rate >= 0.9:
            details.append(f"模块归属完整 ({mod_rate:.0%})")
        else:
            details.append(f"模块归属率 {mod_rate:.0%}")

        # 需求来源
        src_rate = has_source / total if total else 0
        if src_rate >= 0.7:
            details.append(f"需求溯源良好 ({src_rate:.0%})")
        else:
            details.append(f"需求溯源率 {src_rate:.0%}")

        # 综合得分
        score = (pre_rate * 2 + mod_rate * 2 + src_rate * 1) / 5 * 5

        return DimensionScore(
            dimension=ScoreDimension.COMPLETENESS.value,
            score=min(5, score),
            weight=self.weights[ScoreDimension.COMPLETENESS],
            details=details,
        )

    def _score_priority(self, cases: list[dict]) -> DimensionScore:
        """优先级合理性评分.

        检查 P0/P1/P2/P3 分布是否合理。
        """
        details: list[str] = []

        priorities: dict[str, int] = {}
        for case in cases:
            p = str(case.get("priority", "P2")).upper()
            priorities[p] = priorities.get(p, 0) + 1

        total = len(cases)

        # P0 占比不应过高（通常不超过 20%）
        p0_rate = priorities.get("P0", 0) / total if total else 0
        if p0_rate > 0.3:
            details.append(f"P0 占比过高 ({p0_rate:.0%})，建议精简核心用例")
            score = 3.0
        elif p0_rate > 0.2:
            details.append(f"P0 占比合理 ({p0_rate:.0%})")
            score = 4.0
        else:
            details.append(f"P0 占比 {p0_rate:.0%}，核心用例较少")
            score = 4.5

        # 应有 P0-P3 的梯度分布
        levels = sum(1 for p in ["P0", "P1", "P2", "P3"] if priorities.get(p, 0) > 0)
        if levels >= 3:
            details.append(f"优先级梯度合理，覆盖 {levels} 个级别")
        else:
            details.append(f"优先级梯度不够，仅 {levels} 个级别")
            score -= 0.5

        return DimensionScore(
            dimension=ScoreDimension.PRIORITY.value,
            score=max(0, score),
            weight=self.weights[ScoreDimension.PRIORITY],
            details=details,
        )

    def _score_single_case(self, case: dict) -> float:
        """评分单个用例（简化版）."""
        score = 5.0

        # 标题
        title = str(case.get("title", ""))
        if len(title) < 10:
            score -= 0.5

        # 步骤
        steps = case.get("steps", [])
        if len(steps) < 2:
            score -= 1.0
        if not any(len(str(s)) > 5 for s in steps):
            score -= 0.5

        # 预期结果
        expected = str(case.get("expected", ""))
        if len(expected) < 10:
            score -= 1.0

        # 优先级
        priority = str(case.get("priority", "")).upper()
        if priority not in ("P0", "P1", "P2", "P3"):
            score -= 0.5

        return max(0, score)

    def _generate_suggestions(self, dimensions: list[DimensionScore]) -> list[str]:
        """生成改进建议."""
        suggestions: list[str] = []

        for d in dimensions:
            if d.score < 3.0:
                suggestions.append(f"【{d.dimension}】得分较低({d.score:.1f})，优先改进")
            elif d.score < 4.0:
                suggestions.append(f"【{d.dimension}】有提升空间({d.score:.1f})，建议优化")

        if not suggestions:
            suggestions.append("用例质量良好，继续保持")

        return suggestions
