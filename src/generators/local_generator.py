"""基于规则的本地测试用例生成器, 无需 API Key.

通过分析需求文本的结构（标题、功能点描述、约束条件）自动生成测试用例。
作为 ClaudeClient 不可用的降级方案，保证所有 MCP tools 在无 API Key 时也能工作。
"""

import re
from typing import Any


class LocalGenerator:
    """基于规则的本地测试用例生成器.

    通过分析需求文本中的功能点，使用预定义模板自动生成测试用例。
    支持 8 种功能类型：输入、查询、状态、按钮、权限、导出、树形、通用。
    """

    # 功能类型关键词映射
    _KEYWORD_MAP: dict[str, tuple[str, ...]] = {
        "input": ("输入", "填写", "录入", "编辑", "修改"),
        "query": ("查询", "筛选", "搜索", "查找", "条件"),
        "state": ("状态", "流转", "转换", "审核", "审批", "通过", "驳回"),
        "button": ("按钮", "点击", "提交", "保存", "删除", "新增", "创建"),
        "permission": ("权限", "角色", "授权", "用户", "登录", "登出"),
        "export": ("导出", "下载", "excel", "csv"),
        "tree": ("树", "层级", "节点", "展开", "折叠", "导航"),
    }

    # 用例模板定义
    # 每个模板包含：suffix(标题后缀), precondition, steps, expected, priority, type, test_method
    # steps 中可使用 {module} 和 {title} 占位符
    _TEMPLATES: dict[str, list[dict[str, Any]]] = {
        "input": [
            {
                "suffix": "正常数据",
                "precondition": "用户已登录，有操作权限",
                "steps": ["进入{module}页面", "输入合法数据", "执行{title}操作"],
                "expected": "操作成功，数据正确保存/展示",
                "priority": "P0", "type": "功能测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "空值/必填校验",
                "precondition": "用户已登录，有操作权限",
                "steps": ["进入{module}页面", "不输入任何数据", "尝试执行{title}操作"],
                "expected": "系统提示必填字段不能为空，不允许提交",
                "priority": "P1", "type": "容错性测试", "test_method": "边界值分析法",
            },
            {
                "suffix": "超长/边界值数据",
                "precondition": "用户已登录，有操作权限",
                "steps": ["进入{module}页面", "输入超过最大长度的数据", "执行{title}操作"],
                "expected": "系统提示数据长度超出限制或自动截断",
                "priority": "P1", "type": "容错性测试", "test_method": "边界值分析法",
            },
            {
                "suffix": "特殊字符/非法格式",
                "precondition": "用户已登录，有操作权限",
                "steps": ["进入{module}页面", "输入包含特殊字符的数据（如<>!@#$）", "执行{title}操作"],
                "expected": "系统对非法字符进行过滤或给出明确错误提示",
                "priority": "P1", "type": "容错性测试", "test_method": "错误推测法",
            },
            {
                "suffix": "重复提交",
                "precondition": "用户已登录，有操作权限",
                "steps": ["进入{module}页面", "输入合法数据", "快速连续点击提交按钮多次"],
                "expected": "系统防止重复提交，仅处理一次请求",
                "priority": "P2", "type": "容错性测试", "test_method": "错误推测法",
            },
        ],
        "query": [
            {
                "suffix": "精确匹配",
                "precondition": "查询页面已加载，存在目标数据",
                "steps": ["进入{module}页面", "输入精确查询条件", "执行查询"],
                "expected": "查询结果准确匹配条件，无多余或遗漏数据",
                "priority": "P0", "type": "功能测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "模糊匹配",
                "precondition": "查询页面已加载，存在目标数据",
                "steps": ["进入{module}页面", "输入部分关键字", "选择模糊匹配模式", "执行查询"],
                "expected": "查询结果包含所有匹配关键字的记录",
                "priority": "P1", "type": "功能测试", "test_method": "场景法",
            },
            {
                "suffix": "组合条件查询",
                "precondition": "查询页面已加载",
                "steps": ["进入{module}页面", "设置多个筛选条件", "执行查询"],
                "expected": "查询结果同时满足所有筛选条件",
                "priority": "P1", "type": "功能测试", "test_method": "决策表法",
            },
            {
                "suffix": "无结果查询",
                "precondition": "查询页面已加载",
                "steps": ["进入{module}页面", "输入不存在的数据作为查询条件", "执行查询"],
                "expected": "系统提示暂无数据或展示空结果提示",
                "priority": "P2", "type": "易用性测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "清空筛选条件恢复",
                "precondition": "已执行过一次筛选查询",
                "steps": ["点击重置/清除筛选按钮", "查看查询结果"],
                "expected": "筛选条件清空，展示全部数据",
                "priority": "P2", "type": "功能测试", "test_method": "场景法",
            },
        ],
        "state": [
            {
                "suffix": "正常状态流转",
                "precondition": "业务处于初始状态",
                "steps": ["进入{module}", "执行操作触发状态变化", "确认状态更新"],
                "expected": "状态正确流转至目标状态，数据同步更新",
                "priority": "P0", "type": "功能测试", "test_method": "状态转换法",
            },
            {
                "suffix": "退回/拒绝状态流转",
                "precondition": "业务处于中间状态",
                "steps": ["进入{module}", "执行拒绝/退回操作", "确认状态回退"],
                "expected": "状态正确回退至前一状态，业务可重新编辑",
                "priority": "P0", "type": "功能测试", "test_method": "状态转换法",
            },
            {
                "suffix": "无权限操作被拦截",
                "precondition": "使用无权限账号登录",
                "steps": ["进入{module}", "尝试执行{title}操作"],
                "expected": "系统拒绝操作，提示权限不足",
                "priority": "P1", "type": "功能测试", "test_method": "错误推测法",
            },
            {
                "suffix": "并发状态冲突",
                "precondition": "同一业务被多用户同时操作",
                "steps": ["用户A进入{module}执行操作", "同时用户B对同一业务执行操作"],
                "expected": "后操作者收到冲突提示，数据一致性不被破坏",
                "priority": "P1", "type": "功能测试", "test_method": "错误推测法",
            },
        ],
        "button": [
            {
                "suffix": "正常操作",
                "precondition": "页面已加载，有操作权限",
                "steps": ["进入{module}页面", "点击{title}", "确认操作"],
                "expected": "操作执行成功，页面正确响应（跳转/刷新/提示）",
                "priority": "P0", "type": "功能测试", "test_method": "场景法",
            },
            {
                "suffix": "重复点击防重",
                "precondition": "页面已加载",
                "steps": ["进入{module}页面", "快速连续点击{title}多次"],
                "expected": "系统防止重复执行，仅处理一次请求，按钮置灰或loading状态",
                "priority": "P1", "type": "容错性测试", "test_method": "错误推测法",
            },
            {
                "suffix": "操作后取消/撤销",
                "precondition": "操作已执行",
                "steps": ["执行{title}操作", "点击取消/撤销按钮", "确认取消"],
                "expected": "操作被撤销，数据恢复至操作前状态",
                "priority": "P2", "type": "功能测试", "test_method": "场景法",
            },
        ],
        "permission": [
            {
                "suffix": "有权限用户",
                "precondition": "使用有权限账号登录",
                "steps": ["登录有权限账号", "进入{module}", "查看/操作{title}"],
                "expected": "功能正常展示/操作成功",
                "priority": "P0", "type": "功能测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "无权限用户",
                "precondition": "使用无权限账号登录",
                "steps": ["登录无权限账号", "进入{module}", "尝试查看/操作{title}"],
                "expected": "功能隐藏或操作被拒绝，提示权限不足",
                "priority": "P0", "type": "功能测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "权限变更实时生效",
                "precondition": "用户当前在线",
                "steps": ["管理员修改用户权限", "用户刷新页面", "查看权限变化"],
                "expected": "权限变更立即生效，无需重新登录",
                "priority": "P1", "type": "功能测试", "test_method": "场景法",
            },
        ],
        "export": [
            {
                "suffix": "正常导出",
                "precondition": "页面有数据",
                "steps": ["进入{module}页面", "点击导出按钮", "选择保存路径"],
                "expected": "文件下载成功，内容与页面展示一致，格式正确",
                "priority": "P1", "type": "功能测试", "test_method": "场景法",
            },
            {
                "suffix": "大数据量导出",
                "precondition": "页面有大量数据",
                "steps": ["进入{module}页面", "点击导出按钮"],
                "expected": "系统正常处理，导出完整数据，不丢失记录",
                "priority": "P2", "type": "功能测试", "test_method": "边界值分析法",
            },
            {
                "suffix": "空数据导出",
                "precondition": "页面无数据",
                "steps": ["进入{module}页面", "点击导出按钮"],
                "expected": "导出文件包含表头但无数据行，或提示无数据可导出",
                "priority": "P2", "type": "易用性测试", "test_method": "等价类划分法",
            },
        ],
        "tree": [
            {
                "suffix": "展开/折叠节点",
                "precondition": "树形导航已加载",
                "steps": ["点击展开按钮展开一级节点", "点击折叠按钮收起节点"],
                "expected": "节点正确展开显示子节点，折叠后隐藏子节点",
                "priority": "P1", "type": "功能测试", "test_method": "场景法",
            },
            {
                "suffix": "关键字搜索过滤",
                "precondition": "树形导航已加载",
                "steps": ["在搜索框输入关键字", "查看筛选结果"],
                "expected": "树形节点按名称模糊匹配过滤，展示符合条件的节点",
                "priority": "P1", "type": "功能测试", "test_method": "等价类划分法",
            },
            {
                "suffix": "点击节点展示详情",
                "precondition": "树形导航已加载",
                "steps": ["点击某个树节点"],
                "expected": "右侧展示该节点的详细信息或对应页面",
                "priority": "P0", "type": "功能测试", "test_method": "场景法",
            },
        ],
        "generic": [
            {
                "suffix": "正常流程",
                "precondition": "用户已登录，有操作权限，相关数据已准备",
                "steps": ["进入{module}页面", "执行{title}操作", "确认结果"],
                "expected": "操作成功，结果符合预期",
                "priority": "P0", "type": "功能测试", "test_method": "场景法",
            },
            {
                "suffix": "异常流程/无效输入",
                "precondition": "用户已登录",
                "steps": ["进入{module}页面", "输入异常数据或执行异常操作", "确认系统响应"],
                "expected": "系统给出明确错误提示，不崩溃，数据不被破坏",
                "priority": "P1", "type": "容错性测试", "test_method": "错误推测法",
            },
            {
                "suffix": "边界值测试",
                "precondition": "用户已登录",
                "steps": ["进入{module}页面", "输入边界值数据（最大值/最小值/空值）", "确认系统响应"],
                "expected": "系统正确处理边界值，不溢出、不截断、不报错",
                "priority": "P1", "type": "功能测试", "test_method": "边界值分析法",
            },
        ],
    }

    def __init__(self):
        self.case_counter = 0

    def generate(
        self,
        requirement_text: str,
        historical_cases: list[dict] | None = None,
        doc_version: str = "1.0",
    ) -> list[dict[str, Any]]:
        """基于规则生成测试用例.

        Args:
            requirement_text: 结构化需求文本（Markdown）
            historical_cases: 历史用例（本实现忽略，仅保持接口一致）
            doc_version: 需求文档版本号

        Returns:
            测试用例字典列表
        """
        self.case_counter = 0
        cases: list[dict[str, Any]] = []

        features = self._extract_features(requirement_text)
        for feature in features:
            feature_cases = self._generate_feature_cases(feature, doc_version)
            cases.extend(feature_cases)

        # 去重: 按 (module, title) 组合
        seen = set()
        unique_cases = []
        for case in cases:
            key = (case.get("module", ""), case["title"])
            if key not in seen:
                seen.add(key)
                unique_cases.append(case)

        return unique_cases

    def _extract_features(self, text: str) -> list[dict]:
        """从需求文本中提取功能点.

        支持 Markdown 标题 (## / ###) 和中文编号标题 (4. / 4.1 / 5.2.1).
        """
        features = []
        current_module = ""

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Markdown 标题
            m = re.match(r"^(#{2,4})\s*(.+)", line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                if level == 2:
                    current_module = title
                features.append({"module": current_module, "title": title})
                continue

            # 中文编号标题: 4. / 4.1 / 5.12.3
            m = re.match(r"^(\d+(?:\.\d+){0,2})\s+(.+)", line)
            if m:
                section_num, title = m.group(1), m.group(2).strip()
                level = section_num.count(".") + 1
                if level == 1:
                    current_module = title
                features.append({"module": current_module, "title": f"{section_num} {title}"})
                continue

            # 列表项
            m = re.match(r"^[-*]\s*(.+)", line)
            if m:
                features.append({"module": current_module, "title": m.group(1).strip()})

        return features

    def _next_id(self) -> str:
        """生成递增的用例ID."""
        self.case_counter += 1
        return f"TC-{self.case_counter:03d}"

    def _classify_feature(self, title: str) -> str:
        """根据标题内容判断功能类型."""
        t = title.lower()
        for feature_type, keywords in self._KEYWORD_MAP.items():
            if any(k in t for k in keywords):
                return feature_type
        return "generic"

    def _generate_feature_cases(self, feature: dict, doc_version: str) -> list[dict]:
        """为单个功能点生成测试用例."""
        title = feature["title"]
        module = feature.get("module", "")
        feature_type = self._classify_feature(title)

        templates = self._TEMPLATES.get(feature_type, self._TEMPLATES["generic"])
        cases = [self._render_case(title, module, t) for t in templates]

        # 补充元数据
        for case in cases:
            case["status"] = "draft"
            case["doc_version"] = doc_version
            case["review_status"] = "pending"
            if "id" not in case:
                case["id"] = self._next_id()

        return cases

    def _render_case(self, title: str, module: str, template: dict) -> dict:
        """从模板渲染单个用例."""
        return {
            "id": self._next_id(),
            "module": module,
            "title": f"验证{title}（{template['suffix']}）",
            "precondition": template["precondition"],
            "steps": [s.format(title=title, module=module) for s in template["steps"]],
            "expected": template["expected"],
            "priority": template["priority"],
            "type": template["type"],
            "source": f"{module} - {title}",
            "test_method": template["test_method"],
        }
