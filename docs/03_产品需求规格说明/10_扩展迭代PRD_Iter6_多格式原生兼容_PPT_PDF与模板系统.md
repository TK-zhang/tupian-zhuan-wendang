# 扩展迭代 PRD - Iteration 6：多格式原生兼容、PPT/PDF 与模板系统

## 1. 迭代概述与交付目标

### 1.1 业务诉求
不同业务角色的交付载体各不相同：
- **中高层汇报与方案宣讲**：极度依赖结构清晰、图文并茂的 **PowerPoint 演示文稿 (`.pptx`)**；
- **公文归档、招投标底稿与法律审计**：要求绝对固化排版、矢量可缩放且带打印封面的 **标准 PDF (PDF/A)**；
- **极客知识库与技术团队**：深度依赖带 YAML 前置元数据、Mermaid 流程图与双向链接的 **Obsidian/Notion Markdown**；
- **企业品牌定制**：要求一键套用企业内部标准母版、企业专属配色、公司 Logo 页眉页脚及保密水印。
Iteration 6 的核心使命是构建**“多目标格式原生编译器与企业样式模板系统”**，实现从统一底层 DocAST 到多形态交付物的一键无损投射。

### 1.2 阶段验收核心指标
1. **PPT 演示文稿格式合规性**：生成的 `.pptx` 文件在 Microsoft PowerPoint 2016+、Apple Keynote 及 WPS Office 中打开**零样式错位与字体挤压**；
2. **PDF 排版分页严谨性**：严格遵守 A4 页面标准网格，**零标题孤行（Orphan/Widow Heading）**，长表格自动跨页重复表头；
3. **企业模板热插拔耗时**：替换外部企业样式配置文件（`.json` / `.dotx` / `.potx`），编译注入耗时 $\le 500\text{ms}$。

---

## 2. 详细功能需求规格 (Functional Requirements)

### FR-601: 微软原生 OpenXML PowerPoint (`.pptx`) 编译器
- **处理逻辑**：
  - 基于 `python-pptx` 或底层 OpenXML PresentationML 构建；
  - **动态版式识别与映射**：
    - 封面页：自动从文档元数据中提取主标题、副标题、生成日期；
    - 目录页：自动根据 Level 1 标题生成带色块图标的 Agenda 页；
    - 架构/图表页：左侧放置核心说明与要点 Bullet Points，右侧等比例嵌入高精拓扑图或表格；
    - 双栏对比页：针对存在对比项的内容自动渲染为并列卡片容器；
  - **自适应文本缩放与分页 (Auto-Split)**：单页内容若超过 6 行文本或超出页面边界，自动切分为“（续）”页，严禁文字超出幻灯片版心。

### FR-602: 工业级矢量 PDF 排版与打印控制引擎 (High-Precision PDF Engine)
- **处理逻辑**：
  - 采用基于 W3C Paged Media 标准规范（如 WeasyPrint 或基于 Chromium 无头打印管道）；
  - **高级排版规则强制约束**：
    - 页面尺寸与边距：严格 A4（$210\text{mm} \times 297\text{mm}$），外边距标准 $25\text{mm}$；
    - 孤行控制（Orphans & Widows）：段落末行不得单独留在页首，标题必须与正文至少 3 行同页渲染；
    - 表格跨页自愈：长表格跨页时，自动在次页顶部补齐带有样式的重复表头（`thead`）；
    - PDF/A-1b 归档合规：内置字体全量嵌入（Subsetting），保证在任何脱机终端打印的一致性。

### FR-603: 知识管理扩展双链 Markdown 编译器
- **处理逻辑**：
  - 输出兼容 Obsidian / Logseq / Notion 标准的纯文本生态；
  - **YAML Frontmatter 注入**：头部注入生成时间、素材哈希、标签（Tags）、全局关联文档列表；
  - **Mermaid 矢量代码块转换**：针对识别出的简易流程图或时序图，转换为可交互渲染的 `mermaid` 代码块；
  - **Wiki-links 双链语法支持**：将专有名词统一格式化为 `[[概念名称]]`，直接构建本地双链网络。

### FR-604: 企业级视觉规范与样式模板动态注入器 (Enterprise Style Engine)
- **处理逻辑**：
  - 支持导入企业自定义样式包（`theme.json`）：
    - 核心品牌色彩（主色 Primary, 辅色 Secondary, 强调色 Accent）；
    - 企业法定中英文字体（如思源黑体、微软雅黑、Arial）；
    - 封面企业 Logo 矢量图与版位配置；
    - 页眉文档标题、页脚动态“第 X 页 / 共 Y 页”与公司版权声明；
    - 背景平铺半透明防泄密水印（如“内部保密材料·禁止外传”）。

---

## 3. 核心数据契约：样式配置文件 (DocumentStyleProfile Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DocumentStyleProfile",
  "type": "object",
  "properties": {
    "brand_name": { "type": "string", "example": "某国家级能源集团" },
    "color_palette": {
      "primary": "#003366",
      "secondary": "#4A90E2",
      "neutral_dark": "#2C3E50",
      "neutral_light": "#F8F9FA"
    },
    "typography": {
      "font_family_zh": "Source Han Sans CN",
      "font_family_en": "Segoe UI",
      "heading_1_size_pt": 22,
      "heading_2_size_pt": 16,
      "body_size_pt": 10.5,
      "line_spacing": 1.25
    },
    "watermark": {
      "enabled": true,
      "text": "商业绝密·未经许可禁止截屏",
      "opacity": 0.12,
      "angle_deg": -30
    }
  }
}
```

---

## 4. 边界场景与异常防御矩阵

| 边界场景 | 现象描述 | 确定性防御方案 |
| :--- | :--- | :--- |
| **脱机环境缺失指定商用字体** | 模板指定了特定商业字体（如方正兰亭），但离线机器未安装 | 建立字体回退链（Fallback Chain）：`[目标字体] -> 思源黑体 -> 微软雅黑 -> 系统默认等宽字体`，杜绝渲染崩溃 |
| **超大高分辨率插图导致 PPT 体积爆炸** | 嵌入 50 张 4K 手机原图导致生成的 PPTX 超过 300MB | 导出阶段自动执行视口尺寸探测，将图片等比例下采样压缩至 150 DPI（满足投影汇报最佳平衡），体积骤降 80% |
| **表格列数超过 PPT 版心限制** | 12 列表格横向放置在 16:9 幻灯片中会发生文字重叠重合 | 自动切分为“主表 + 附表”多卡片展现，或自动缩小单元格字号并增加水平滚动条样式 |
