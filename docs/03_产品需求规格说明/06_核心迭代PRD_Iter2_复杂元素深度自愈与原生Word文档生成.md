# 核心迭代 PRD - Iteration 2：复杂元素深度自愈与原生 Word 文档生成

## 1. 迭代概述与交付目标

### 1.1 业务诉求
Iteration 1 解决了纯文本与基础区块的提取，但在政企和企业生产环境中，文档的核心价值高度集中在**“复杂表格、数学物理公式、高保真架构拓扑插图、带缩进的代码片段”**以及**“符合企业级规范的 Word (`.docx`) 原生交付件”**。
Iteration 2 聚焦于攻克复杂组件的几何与语义解析，引入确定性 AST 语法自愈算法消除模型误读，并基于底层 OpenXML 二进制协议构建直接生成可编辑 Word 的专业排版引擎。

### 1.2 阶段验收核心指标
1. **复杂表格网格解析率**：跨行跨列（Colspan/Rowspan）及多级表头的物理对齐准确率 $\ge 92\%$；
2. **代码语法错误自愈率**：由光线反光、遮挡引起的语法破坏（如括号不闭合、保留字误识），经 AST 纠偏后修复率 $\ge 85\%$；
3. **Word 文档标准兼容性**：输出的 `.docx` 文件在 Microsoft Office 2016/2019/2021/365 及 WPS Office 中打开**零 XML 语法破坏性弹窗警告**，样式与大纲导航窗格 100% 完整映射。

---

## 2. 详细功能需求规格 (Functional Requirements)

### FR-201: 复杂表格几何网格对齐与单元格合并解析 (Table Grid Decomposition)
- **处理逻辑**：
  - 针对版面分析识别出的 `table` 区块，执行骨架线与物理单元格探测；
  - 提取表格的虚拟网格坐标系（Grid Rows $\times$ Grid Cols）；
  - **跨行跨列合并检测**：对无边框或隐式分割的跨行（Rowspan）、跨列（Colspan）表头，结合视觉边界框与文本投影直方图进行拓扑推导；
  - 单元格内换行自愈：提取每个单元格内的多行文本，保持垂直居中/靠左对齐属性；
- **输出**：输出规范化的 `TableGridNode` 结构，附带精确的 `row_span` 和 `col_span` 属性。

### FR-202: 数学与物理公式 LaTeX 标准化 (Mathematical Formula Extraction)
- **处理逻辑**：
  - 识别行内公式（Inline Formula）与独占行独立公式（Display Formula）；
  - 将图像中的上下标、积分号、矩阵、希腊字母统一编译为标准 KaTeX / MathJax 兼容的 LaTeX 表达式字符串；
  - 针对 Word 导出，内置将 LaTeX 字符串自动编译为 Office OpenXML 原生公式标记（`m:oMath`）的转换器，保证在 Word 中直接可双击编辑。

### FR-203: 矢量拓扑与高精插图自动裁切保存 (Illustration Auto-Cropping & Asset Management)
- **处理逻辑**：
  - 针对版面标记为 `image_region` 的插图、截屏、拓扑图，计算其绝对物理像素边界；
  - 执行原始高清图像的无损无压缩裁切（Crop）；
  - 自动执行图像质量优化：300 DPI 元数据注入、边缘锐化、白底归一化；
  - 将裁切后的资产保存至项目工作区的 `assets/` 目录，命名规则为 `{doc_id}_img_{block_id}.png`；
  - 在 DocAST 中记录相对路径及长宽物理显示比例。

### FR-204: 计算机代码块 AST 语法树纠偏与自愈 (Deterministic AST Syntax Rectification)
- **处理逻辑**：
  - 针对被识别为 `code_block` 的内容，首先进行编程语言判定（Python, SQL, JSON, Java, C/C++ 等）；
  - 调用特定语言的轻量词法解析器（如 Python `ast.parse`，Tree-sitter 词法树）；
  - **规则字典辅助修复**：
    - 针对高频视觉混淆字符建立纠错映射（例如：在 Python 循环中 `f0r` $\to$ `for`, `whi1e` $\to$ `while`；在变量命名中将数字 `1O` 修复为 `10`）；
    - 括号与引号对称性闭合检测：若行末由于阴影丢失闭合单引号或大括号，通过词法栈自动补全；
  - 若解析成功，标记为 `syntax_verified: true`；若修复失败，保留原样并添加代码警告注释，严禁臆造代码。

### FR-205: 微软原生 OpenXML Word (`.docx`) 排版编译器
- **处理逻辑**：
  - 拒绝通过低质量的 HTML-to-Docx 中转，直接基于 `python-docx` 或底层 XML 打包构建标准的 `.docx` 容器；
  - **样式规范强制绑定**：
    - `heading_1`：绑定“标题 1”原生样式（小二号黑体，段前 12pt，段后 6pt，大纲级别 1）；
    - `heading_2`：绑定“标题 2”原生样式（三号黑体，段前 6pt，段后 3pt，大纲级别 2）；
    - `paragraph`：首行缩进 2 字符，正文宋体/等线 10.5pt，1.25 倍行距；
    - `table`：套用标准企业三线表样式，首行加粗着色，自动适应页面宽度，单元格文字垂直居中；
    - `code_block`：创建浅灰底色（`#F4F4F4`）单行表格或段落底纹，字体统一为 Consolas / Courier New，保留严格缩进；
    - `image_region`：按 Word 页面版心宽度自动等比例缩放居中嵌入。

---

## 3. 核心数据契约：DocAST v2.0 增量节点定义

```json
{
  "block_id": "blk_0042",
  "type": "table",
  "bbox": [210, 50, 680, 950],
  "table_data": {
    "rows": 4,
    "cols": 3,
    "grid": [
      [
        { "text": "模块名称", "row_span": 1, "col_span": 1, "is_header": true },
        { "text": "输入输出接口规范", "row_span": 1, "col_span": 2, "is_header": true }
      ],
      [
        { "text": "认证中心", "row_span": 2, "col_span": 1, "is_header": false },
        { "text": "POST /api/v1/login", "row_span": 1, "col_span": 1, "is_header": false },
        { "text": "JWT 签名凭证", "row_span": 1, "col_span": 1, "is_header": false }
      ],
      [
        { "text": "GET /api/v1/verify", "row_span": 1, "col_span": 1, "is_header": false },
        { "text": "公钥证书验签状态", "row_span": 1, "col_span": 1, "is_header": false }
      ]
    ]
  }
}
```

---

## 4. 边界场景与异常防御矩阵

| 边界场景 | 现象描述 | 确定性防御方案 |
| :--- | :--- | :--- |
| **残缺表格（跨页截断）** | 表格底部只有一半边框，下半部分在下一张照片 | 标记 `table_status: "truncated_bottom"`，暂存至 AST 待聚合池，等待后续页面合并 |
| **超宽表格** | 列数 $> 10$ 列，直接放入纵向 Word 会导致文字严重挤压折行 | 编译器自动将该表格所在节（Section）的页面方向设置为**横向（Landscape）** |
| **极端混淆手写字符** | 物理模糊导致无法区分英文字母 `O` 与数字 `0` | 结合上下文词法距离与拼写词典加权决策，若置信度低于 0.6，则保持标注并在调试视图中高亮提示 |
| **无效/破坏性 LaTeX** | 提取出的公式包含未定义的宏包指令 | 自动将异常公式降级包裹在 `\text{...}` 中，防止渲染器崩溃崩溃退出 |
