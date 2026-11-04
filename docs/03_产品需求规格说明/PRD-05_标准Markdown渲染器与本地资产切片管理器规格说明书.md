# 详细需求规格说明书 - PRD-05：标准 Markdown 渲染器与本地资产切片管理器

## 1. 需求基本信息与版本管理

| 属性项 | 内容描述 |
| :--- | :--- |
| **需求代号** | `REQ-MD-EXPORTER-05` (简称 **PRD-05**) |
| **模块归属** | 文档格式渲染与物理资产管理流水线 (`src/exporter/`) |
| **需求版本** | `v1.0.0` (商业生产级规约) |
| **前置依赖** | [PRD-04: 核心DocAST内存数据模型与状态机](file:///c:/Users/zhangtengkuan/Desktop/自己的项目/图片转文档/docs/03_产品需求规格说明/PRD-04_核心DocAST内存数据模型与状态机规格说明书.md) 输出的已校验 AST 树 |
| **后续交付** | 交付第一阶段端到端可验证的物理成品：`output/{doc_id}.md` 及配套资产目录 `output/assets/` |

---

## 2. 业务背景、痛点与核心价值

### 2.1 真实业务痛点剖析
很多声称具备“文档转换”的工具在最终导出环节粗制滥造，留给用户极差的使用体验：
1. **插图资产断层与死链**：文档中提到的架构图、拓扑草图未被物理提取保存，或者直接以 Base64 超长字符串塞进 Markdown 中，导致 `.md` 文本膨胀至数十兆甚至卡死编辑器；
2. **相对路径引用破裂**：图片引用的路径写死为绝对路径（如 `file:///C:/Users/...`），导致文档发给同事或换一台电脑后全量图片变成裂图红叉；
3. **缺乏标准化 Frontmatter 元数据**：导出的 Markdown 没有生成时间、底片哈希、标签等元数据，无法直接接入 Obsidian / Logseq 等本地双链知识库生态；
4. **语法规范混乱**：标题井号后面缺少空格（如 `#标题`），代码块没有标注语言高亮，粗体标记在标点符号间逃逸，破坏排版美感。

### 2.2 模块商业与技术价值
- **交付首个物理闭环成品**：作为第一大阶段的收官模块，完成从散乱输入到高可读性、标准排版 Markdown 文档与本地高清切片素材的端到端贯通；
- **高保真资产归档**：针对拓扑图与插图，执行原始高清原图的无损物理裁切，并注入 300 DPI 印刷级元数据，形成结构化图像资产库；
- **纯本地绝对合规**：全流程在本地工作区完成物理落盘，零网络外联，100% 适配涉密离线与极客个人隐私诉求。

---

## 3. 渲染管线与交付目录物理拓扑

```mermaid
flowchart TD
    A[已校验的DocAST实例] --> B[PRD-05 渲染器流水线]
    B --> C[AST节点遍历与GFM语法映射]
    B --> D[ImageNode物理定位与高清切片裁切]
    D --> E[注入 300 DPI Exif 元数据]
    E --> F[落盘至 ./output/assets/{doc_id}_img_{id}.png]
    C --> G[生成 YAML Frontmatter 头部]
    G --> H[拼接规范相对路径引用 ![caption](./assets/...)]
    H --> I[生成 UTF-8 无BOM 标准 .md 文件]
```

物理交付输出目录规约：
```text
output/
├── 20261105_系统架构设计说明书.md        # 核心交付文档
└── assets/                                # 关联高保真切片资产目录
    ├── doc_01_img_blk_0012.png           # 300 DPI 架构图切片
    └── doc_01_img_blk_0018.png           # 300 DPI 拓扑图切片
```

---

## 4. 详细功能需求规格 (Functional Requirements)

### FR-05-01: GFM / CommonMark 标准语法序列化映射
- **映射规则矩阵**：
  1. `HeadingNode`: 严格按照 `level` 生成对应数量的 `#` 前缀，**强制与标题文字间隔一个空格**（如 `## 2. 核心模块设计`）；末尾追加标准 HTML 锚点标签 `{#sec-heading-id}`；
  2. `ParagraphNode`: 正文自然段落，段落与段落之间保持且仅保持 **1 个标准空行（双换行 `\n\n`）**；低置信度字符区间自动包裹为警示样式标记；
  3. `CodeBlockNode`: 严格使用三个反引号 ```` ```lang ```` 包裹，必须显式标注识别出的编程语言标识符；代码正文保持原样换行与缩进；
  4. `ListNode`: 有序列表映射为 `1. `，无序列表映射为 `- `；嵌套子项严格以 2 空格或 4 空格对齐；
  5. `ImageNode`: 映射为标准 Markdown 相对路径引用：
     ```markdown
     ![架构时序交互图](./assets/doc_01_img_blk_0012.png)
     *图 1: 架构时序交互图 (来源: 原始底片 DSC_0942.JPG)*
     ```

### FR-05-02: 插图/拓扑图高精无损裁切与 300 DPI 固化
- **处理逻辑**：
  - 遍历 AST 中所有 `node_type == "image"` 的节点；
  - 提取其原始像素物理外接框：`[ymin, xmin, ymax, xmax]`；
  - 从 [PRD-01] 预处理后的未缩放高清底片中执行无损矩阵切片：
    ```python
    cropped_patch = raw_image[ymin:ymax, xmin:xmax]
    ```
  - **DPI 元数据注入**：使用 PIL / Pillow 为切片注入横向与纵向 300 DPI 打印级分辨率元数据；
  - 保存格式强制为无损压缩 **PNG 格式**，存储路径为 `output/assets/{doc_id}_img_{node_id}.png`；
  - 更新 AST 中对应节点的 `asset_rel_path = "./assets/{doc_id}_img_{node_id}.png"`。

### FR-05-03: YAML Frontmatter 头部元数据注入
- **处理逻辑**：
  - 在导出的 Markdown 文件起始处（第 1 行）注入标准的 YAML Frontmatter，格式严谨：
    ```markdown
    ---
    title: "微服务架构与数据流设计规范"
    doc_id: "doc_arch_001"
    created_at: "2026-11-05T02:40:00Z"
    generator: "DocReconstruct Engine v1.0"
    source_count: 3
    source_hashes:
      - "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    tags:
      - "架构设计"
      - "自动重构"
    ---
    ```

### FR-05-04: 交付文件完整性与自检校验 (Export Verification)
- **校验逻辑**：
  - 文件写盘完成后，触发自动一致性验证器（Integrity Checker）：
  1. 验证生成的 `.md` 文件大小 $> 0\text{ 字节}$，且编码为严格的 UTF-8 without BOM；
  2. 提取 Markdown 中所有 `![](...)` 相对路径，逐一检测目标物理图片在 `output/assets/` 中是否存在且文件体积 $> 0$；
  3. 若存在任何断链（Broken Image），立即抛出 `ERR-EXP-003` 并记录缺失切片定位。

---

## 5. 字段级数据字典与契约 (Data Contract)

渲染导出完成后的结果元数据模型：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MarkdownExportResult",
  "type": "object",
  "required": [
    "export_id",
    "doc_id",
    "markdown_file_path",
    "markdown_file_size_bytes",
    "exported_assets",
    "export_duration_ms"
  ],
  "properties": {
    "export_id": { "type": "string" },
    "doc_id": { "type": "string" },
    "markdown_file_path": { "type": "string" },
    "markdown_file_size_bytes": { "type": "integer", "minimum": 1 },
    "total_headings": { "type": "integer" },
    "total_paragraphs": { "type": "integer" },
    "total_code_blocks": { "type": "integer" },
    "exported_assets": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["node_id", "asset_file_path", "width_px", "height_px", "size_bytes"],
        "properties": {
          "node_id": { "type": "string" },
          "asset_file_path": { "type": "string" },
          "width_px": { "type": "integer" },
          "height_px": { "type": "integer" },
          "size_bytes": { "type": "integer" }
        }
      }
    },
    "export_duration_ms": { "type": "number" }
  }
}
```

---

## 6. 内部接口与函数契约 (Python API)

```python
from dataclasses import dataclass
from typing import List, Optional
import os

@dataclass
class ExportConfig:
    output_dir: str = "./output"
    assets_dir_name: str = "assets"
    include_yaml_frontmatter: bool = True
    inject_heading_anchors: bool = True
    default_dpi: int = 300

@dataclass
class ExportResult:
    markdown_path: str
    asset_paths: List[str]
    total_characters: int
    is_verified: bool

class MarkdownExporter:
    def __init__(self, config: Optional[ExportConfig] = None) -> None:
        self.config = config or ExportConfig()
        os.makedirs(os.path.join(self.config.output_dir, self.config.assets_dir_name), exist_ok=True)

    def export(self, doc_ast: "DocAST", source_image_map: dict) -> ExportResult:
        """
        执行端到端物理渲染导出：
        1. 遍历DocAST，针对image节点提取底片切片并持久化至assets/
        2. 生成YAML Frontmatter元数据头部
        3. 将节点逐一编译为GFM标准语法并写入.md文件
        4. 执行物理死链自检校验，返回完整性状态
        """
        ...
```

---

## 7. 异常分类与全量错误码字典

| 错误码 | 异常类别 | 触发具体条件 | 业务影响 | 恢复与降级策略 |
| :--- | :--- | :--- | :--- | :--- |
| **ERR-EXP-001** | 输出目录只读/权限不足 | 操作系统无权在目标路径创建文件 | 导出失败中断 | 自动降级尝试当前工作区 `./tmp_output/`，抛出权限告警 |
| **ERR-EXP-002** | 切片坐标越界 | AST 记录的 BBox 超出底片原始真实像素范围 | 切片引发数组越界 | 自动对切片坐标与图像真实长宽执行安全 `clip` 钳制 |
| **ERR-EXP-003** | 资产引用死链自检失败 | 写入的相对路径在物理磁盘未找到对应切片 | Markdown 展现为裂图 | 阻断导出，自动回滚重试裁切流水线 |
| **ERR-EXP-004** | 磁盘存储空间不足 | 写入过程中检测到磁盘剩余空间 $< 50\text{MB}$ | 产生半截残缺文件 | 立即清理本次未完成的临时碎片，提示“磁盘空间不足” |

---

## 8. 边界测试用例与量化验收准则

### 8.1 边界测试用例矩阵

| 用例 ID | 测试输入素材特征 | 预期输出与验收断言 |
| :--- | :--- | :--- |
| **TC-EXP-01** | 包含 2 个一级标题、3 个段落、1 个 Python 代码块的 AST 树 | 导出的 `.md` 文件在 VS Code Markdown Preview 中完美渲染；标题、正文、代码高亮 100% 正确；段落之间严格空 1 行。 |
| **TC-EXP-02** | 包含 1 个架构草图 `ImageNode` 的 AST 树 | `output/assets/` 下成功生成 PNG 切片；图片头信息确认包含 300 DPI 标记；Markdown 中相对引用 `./assets/...` 路径有效命中。 |
| **TC-EXP-03** | 特殊字符与代码反引号转义：代码中包含连续 3 个反引号 ```` ``` ```` | 渲染器自动提升外层代码围栏为 4 个反引号 ```` ```` ````，防止代码块被非预期提前闭合破坏。 |

### 8.2 验收量化指标 (Gate Criteria)
1. **语法渲染合法率**：输出的 `.md` 文件在标准 CommonMark 校验器（如 `markdownlint`）下合规评分 $\ge 98$ 分；
2. **死链发生率**：切片插图物理相对引用断链率为严格的 $0.0\%$；
3. **导出执行耗时**：万字长文附带 10 张高清切片资产，整套导出写入与完整性自检耗时 $\le 250\text{ms}$。
