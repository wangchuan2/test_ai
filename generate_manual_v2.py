#!/usr/bin/env python3
"""重构操作使用手册 v2.0"""

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# 设置默认字体
style = doc.styles['Normal']
font = style.font
font.name = 'Microsoft YaHei'
font.size = Pt(10.5)
style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

# === 封面 ===
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('需求文档驱动测试用例生成系统')
run.font.size = Pt(22)
run.font.bold = True
run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('操作使用手册')
run.font.size = Pt(18)
run.font.bold = True
run.font.color.rgb = RGBColor(0x44, 0x72, 0xC4)

doc.add_paragraph()
info = doc.add_paragraph()
info.alignment = WD_ALIGN_PARAGRAPH.CENTER
info.add_run('Version 2.0\n').font.size = Pt(12)
info.add_run('2026年5月').font.size = Pt(12)

doc.add_page_break()

# === 目录 ===
doc.add_heading('目录', level=1)
toc_items = [
    '一、系统概述',
    '二、快速开始（无 API Key）',
    '三、环境安装与配置',
    '四、核心功能使用指南',
    '五、MCP Server 注册与使用',
    '六、数据目录结构',
    '七、常见问题',
    '八、附录',
]
for item in toc_items:
    doc.add_paragraph(item, style='List Bullet')

doc.add_page_break()

# === 一、系统概述 ===
doc.add_heading('一、系统概述', level=1)
doc.add_paragraph(
    '本系统是一款基于 AI 大模型的测试用例自动生成工具，专为测试工程师设计。'
    '系统支持解析 PDF、Excel、Word、图片等多种格式的需求文档，'
    '运用资深测试专家的系统化方法论，自动生成高覆盖率、高质量的功能测试用例。'
)

doc.add_heading('1.1 双模式架构', level=2)
doc.add_paragraph('系统支持两种工作模式，灵活适配不同场景：')

doc.add_paragraph('模式一：LLM 智能生成（推荐）', style='List Bullet').runs[0].font.bold = True
doc.add_paragraph(
    '配置 Claude/Kimi API Key 后，调用大模型生成高质量、语义精准的测试用例。'
    '支持历史用例注入以保持风格一致性。',
    style='List Bullet 2'
)

doc.add_paragraph('模式二：本地规则生成（零配置）', style='List Bullet').runs[0].font.bold = True
doc.add_paragraph(
    '无需 API Key，内置基于规则的本地生成引擎自动分析需求文本，'
    '按功能类型（输入/查询/状态/权限等）匹配测试模板，快速生成标准化用例。'
    '适合无网络环境或保密场景。',
    style='List Bullet 2'
)

doc.add_heading('1.2 设计原则', level=2)
principles = [
    '仅聚焦功能测试范畴，不生成性能、安全相关测试内容',
    '运用七大系统化测试设计方法（等价类、边界值、决策表、状态转换、正交试验、场景法、错误推测）',
    '高覆盖率保障：需求覆盖率100%、边界覆盖率100%、业务规则覆盖率100%、功能覆盖率≥95%、异常覆盖率≥90%',
    '模块化设计思路，保证结构清晰，支持长期维护优化',
    '预留测试空间，覆盖突发情况与非常规测试场景',
]
for p in principles:
    doc.add_paragraph(p, style='List Bullet')

# === 二、快速开始 ===
doc.add_heading('二、快速开始（无 API Key）', level=1)
doc.add_paragraph('系统默认启用本地规则生成模式，无需任何配置即可使用。')

steps = [
    ('安装依赖', 'pip install -e .'),
    ('启动 MCP Server', 'python -m mcp_server.server'),
    ('对话调用', '在 Claude Code 中直接说：\n"解析需求文档并生成测试用例"'),
    ('查看结果', '生成的用例保存在 data/test_cases/ 目录下'),
]
for i, (title, content) in enumerate(steps, 1):
    p = doc.add_paragraph(style='List Number')
    p.add_run(title).bold = True
    doc.add_paragraph(content, style='List Bullet 2')

doc.add_paragraph()
note = doc.add_paragraph()
note.add_run('提示：').bold = True
note.add_run('如需使用 LLM 模式生成更高质量用例，请参考第三章配置 API Key。')

# === 三、环境安装 ===
doc.add_heading('三、环境安装与配置', level=1)

doc.add_heading('3.1 依赖安装', level=2)
doc.add_paragraph('确保 Python 3.10+ 环境，执行以下命令安装依赖：')
code = doc.add_paragraph()
code.paragraph_format.left_indent = Inches(0.3)
code.paragraph_format.space_before = Pt(6)
code.paragraph_format.space_after = Pt(6)
# 浅灰色背景模拟代码块
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
shading_elm = parse_xml(r'<w:shd {} w:fill="F5F5F5"/>'.format(nsdecls('w')))
code._p.get_or_add_pPr().append(shading_elm)
code_run = code.add_run('pip install -e .')
code_run.font.name = 'Consolas'
code_run.font.size = Pt(10)

doc.add_paragraph(
    '系统已配置 pyproject.toml，一键安装所有依赖（包括 anthropic、openai、fastmcp 等）。'
)

doc.add_heading('3.2 API Key 配置（可选）', level=2)
doc.add_paragraph(
    'LLM 模式需要配置 API Key。本地规则模式无需此步骤。'
)

doc.add_paragraph('Anthropic Claude:', style='List Bullet')
code = doc.add_paragraph('set ANTHROPIC_API_KEY=sk-ant-xxxxx', style='List Bullet 2')
code.runs[0].font.name = 'Consolas'

doc.add_paragraph('Kimi (OpenAI 兼容):', style='List Bullet')
code = doc.add_paragraph('set OPENAI_API_KEY=sk-xxxxx', style='List Bullet 2')
code.runs[0].font.name = 'Consolas'

doc.add_paragraph(
    '或在调用 generate_test_cases 时传入 api_key 参数。'
)

doc.add_heading('3.3 MCP Server 配置', level=2)
doc.add_paragraph(
    '项目已内置 MCP 配置文件 .claude/mcp.json，Claude Code 会自动识别。'
    '如需手动注册：'
)
code = doc.add_paragraph()
code.add_run('claude mcp add test-case-generator -- python e:/test_ai/mcp_server/server.py').font.name = 'Consolas'

# === 四、核心功能 ===
doc.add_heading('四、核心功能使用指南', level=1)

functions = [
    ('4.1 需求文档解析',
     '将 PDF、Excel、Word、图片解析为结构化 Markdown。',
     'parse_document(file_path="path/to/requirement.pdf")',
     'PDF / Excel / Word / 图片'),
    ('4.2 需求模块拆分',
     '按标题层级拆分为独立子需求模块。',
     'split_requirement(doc_name="requirement")',
     '输出：data/parsed/split/{doc_name}/'),
    ('4.3 测试用例生成',
     '基于需求生成结构化测试用例 JSON。无 API Key 时自动使用本地规则引擎。',
     'generate_test_cases(doc_name="requirement")\ngenerate_test_cases(doc_name="requirement", use_split=True)',
     '输出：data/test_cases/{doc_name}_cases.json'),
    ('4.4 Excel 导出',
     '导出为标准 Excel，支持多 Sheet 和优先级颜色。',
     'export_to_excel(doc_name="requirement")',
     '输出：data/test_cases/{doc_name}_test_cases.xlsx'),
    ('4.5 文档变更检测',
     '语义级对比新旧版本，识别增删改。',
     'detect_doc_changes(doc_name="requirement", new_file_path="path/to/v2.pdf")',
     '输出：变更报告 Markdown + diff JSON'),
    ('4.6 用例自动同步',
     '根据变更检测结果，标记用例状态（新增/Review/废弃）。',
     'sync_test_cases(doc_name="requirement", new_doc_name="requirement_v2")',
     '输出：同步后用例 JSON + 同步报告'),
    ('4.7 规则校验',
     '12 条内置规则自动校验用例完整性。',
     'validate_cases(doc_name="requirement")',
     '输出：校验报告'),
    ('4.8 质量评分',
     '五维度评分（覆盖率、可执行性、准确性、完整性、优先级）。',
     'score_case_quality(doc_name="requirement")',
     '输出：评分报告'),
]

for title, desc, cmd, output in functions:
    doc.add_heading(title, level=2)
    doc.add_paragraph(desc)
    doc.add_paragraph('调用方式：').runs[0].bold = True
    code = doc.add_paragraph(cmd)
    code.runs[0].font.name = 'Consolas'
    doc.add_paragraph('输出：' + output)

# === 五、MCP Server ===
doc.add_heading('五、MCP Server 注册与使用', level=1)
doc.add_paragraph(
    '注册后可在 Claude Code 中通过自然语言调用所有功能，无需记忆命令。'
)

doc.add_heading('5.1 自动配置（推荐）', level=2)
doc.add_paragraph(
    '项目根目录已包含 .claude/mcp.json，Claude Code 启动时自动加载。'
)

doc.add_heading('5.2 自然语言调用示例', level=2)
examples = [
    '帮我解析这个 PDF 需求文档并生成测试用例',
    '将需求文档按模块拆分，然后逐个生成用例',
    '把生成的测试用例导出成 Excel',
    '检测需求文档是否有变更，更新对应的测试用例',
    '校验刚才生成的测试用例质量',
    '给这批用例打个质量分',
]
for ex in examples:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run('"').font.italic = True
    p.add_run(ex).font.italic = True
    p.add_run('"').font.italic = True

doc.add_heading('5.3 可用 Tools 列表', level=2)
tools = [
    'parse_document — 解析需求文档',
    'split_requirement — 拆分需求模块',
    'generate_test_cases — 生成测试用例',
    'export_to_excel — 导出 Excel',
    'detect_doc_changes — 检测文档变更',
    'sync_test_cases — 同步用例',
    'validate_cases — 规则校验',
    'score_case_quality — 质量评分',
    'list_documents — 列出已解析文档',
    'list_test_cases — 列出已生成用例',
]
for t in tools:
    doc.add_paragraph(t, style='List Bullet')

# === 六、数据目录 ===
doc.add_heading('六、数据目录结构', level=1)
doc.add_paragraph('系统数据按以下目录结构组织：')

dir_tree = '''data/
├── requirements/          # 原始需求文档（用户上传）
├── parsed/                # 解析后的结构化文本
│   ├── {doc_name}.md      # 完整文档 Markdown
│   └── split/             # 拆分后的子需求
│       └── {doc_name}/
│           ├── {doc_name}_index.json
│           └── {doc_name}_*.md
└── test_cases/            # 生成的测试用例
    ├── {doc_name}_cases.json
    ├── {doc_name}_test_cases.xlsx
    ├── {doc_name}_diff.json
    ├── {doc_name}_change_report.md
    ├── {doc_name}_impact.json
    ├── {doc_name}_sync_report.md
    ├── {doc_name}_validation.json
    └── {doc_name}_quality.json'''

code = doc.add_paragraph(dir_tree)
code.runs[0].font.name = 'Consolas'
code.runs[0].font.size = Pt(9)

# === 七、常见问题 ===
doc.add_heading('七、常见问题', level=1)

qa = [
    ('Q: 没有 API Key 能用吗？',
     'A: 完全可以。系统默认使用本地规则生成引擎，无需任何 API Key 即可生成测试用例。'
     '如需更高质量的 LLM 生成，可配置 Claude/Kimi API Key。'),
    ('Q: 生成的用例质量不高怎么办？',
     'A: 1) 确保需求文档解析完整；2) 配置 API Key 使用 LLM 模式；'
     '3) 提供历史用例 Excel 到 data/historical_cases/ 作为风格参考；'
     '4) 使用 score_case_quality 查看评分并针对性优化。'),
    ('Q: 大型需求文档如何处理？',
     'A: 建议先用 split_requirement 拆分文档，再用 generate_test_cases 的 use_split=True 参数逐个模块生成。'),
    ('Q: 需求变更后如何更新用例？',
     'A: 1) detect_doc_changes 检测变更；2) sync_test_cases 分析影响并标记状态；'
     '3) 根据报告建议操作（新增/Review/废弃）。'),
    ('Q: 如何扩展自定义校验规则？',
     'A: 在 RuleEngine 的 _build_builtin_rules 方法中添加新的 Rule 对象，或调用 add_rule() 动态添加。'),
    ('Q: 支持哪些操作系统？',
     'A: Windows 10/11、macOS、Linux。Python 3.10+ 环境。'),
]

for q, a in qa:
    p = doc.add_paragraph()
    p.add_run(q).bold = True
    doc.add_paragraph(a, style='List Bullet 2')

# === 八、附录 ===
doc.add_heading('八、附录', level=1)

doc.add_heading('8.1 七大测试设计方法速查', level=2)
methods = [
    '等价类划分法 — 区分有效/无效等价类',
    '边界值分析法 — 核验数值/字符串/时间边界',
    '决策表法 — 多条件组合覆盖',
    '状态转换法 — 状态流转路径校验',
    '正交试验法 — 多因素交叉精简',
    '场景法 — 主流程/异常分支/边界',
    '错误推测法 — 预判高风险场景',
]
for m in methods:
    doc.add_paragraph(m, style='List Bullet')

doc.add_heading('8.2 优先级定义', level=2)
priorities = [
    'P0 — 核心业务流程，必须100%覆盖',
    'P1 — 重要功能节点，必须覆盖',
    'P2 — 辅助功能，选择性覆盖',
    'P3 — 边缘场景，抽样覆盖',
]
for p in priorities:
    doc.add_paragraph(p, style='List Bullet')

doc.add_heading('8.3 版本历史', level=2)
history = [
    'v2.0 (2026-05-26) — 新增本地规则生成模式，无需 API Key；重构代码架构；修复多处类型安全问题',
    'v1.0 (2026-05-25) — 初始版本，支持 LLM 生成、Excel 导出、变更检测',
]
for h in history:
    doc.add_paragraph(h, style='List Bullet')

doc.add_heading('8.4 联系方式', level=2)
doc.add_paragraph('如有问题或建议，请通过以下方式反馈：')
doc.add_paragraph('GitHub Issues: https://github.com/your-org/test-case-generator/issues', style='List Bullet')
doc.add_paragraph('邮箱: test-team@example.com', style='List Bullet')

# 保存
output_path = '操作使用手册_v2.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
