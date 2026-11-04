# 核心迭代 PRD - Iteration 1：单图基础识别与结构化 Markdown 流水线

## 1. 迭代概述与交付目标

### 1.1 业务诉求
作为整个系统的基石，Iteration 1 旨在跑通**“原始散乱单张图片 -> 几何增强与预处理 -> 视觉版面分析与文字识别 -> 基础抽象语法树 (DocAST v1.0) 转换 -> 标准 Markdown 渲染输出”**的最简核心业务闭环。
该迭代验证系统的核心吞吐能力与底层抽象数据结构的稳定性，不引入复杂的视频处理、宏观重组织或多格式混排，确保第一步绝对稳固。

### 1.2 阶段验收核心指标
1. **字符识别准确率 (1 - CER)**：印刷体中文与英文字符识别准确率 $\ge 96\%$；
2. **版面区块分割准确率**：段落、一级至三级标题、代码块、列表的分类准确率 $\ge 92\%$；
3. **单图处理端到端耗时**：
   - GPU 模式（RTX 4060 / 16GB 统一显存）：$\le 3.5\text{s}$ / 2K 图像；
   - CPU 模式（Intel i7 / 8 核）：$\le 6.0\text{s}$ / 2K 图像。

---

## 2. 系统输入规范与前置校验

### 2.1 格式与尺寸约束
- **支持文件格式**：`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`。
- **图像分辨率范围**：
  - 最小分辨率：$400 \times 400\text{ px}$（低于此阈值直接触发异常，防止过低质量素材耗费推理算力）；
  - 最大分辨率：$8192 \times 8192\text{ px}$（超过此阈值自动等比例自适应下采样至长边 $4096\text{ px}$）。
- **单文件体积限制**：$\le 50\text{ MB}$。

### 2.2 前置图像预处理规约
1. **EXIF 旋转方向归一化**：解析图像 EXIF Orientation 标记，强制无损旋转至正向（0 度）；
2. **透视畸变轻度纠偏 (Deskewing)**：通过霍夫变换（Hough Line Transform）检测文本行主偏角，在 $\pm 15^\circ$ 范围内执行仿射变换校平；
3. **自适应对比度受限直方图均衡化 (CLAHE)**：针对暗光拍摄或背光屏幕，执行局部动态范围增强，抑制反光光斑。

---

## 3. 详细功能需求规格 (Functional Requirements)

### FR-101: 视觉版面分析与区块分割 (Visual Layout Segmentation)
- **输入**：归一化处理后的高精 RGB 图像。
- **处理逻辑**：
  - 调用版面分析模型（如基于 YOLOv10-DocLayout 或 LayoutLM 精简模型），检测图像中的物理结构块（Blocks）；
  - 为每个区块生成全局归一化外接矩形框坐标：`bbox: [ymin, xmin, ymax, xmax]`，取值范围 $[0, 1000]$；
  - 标记区块类型枚举值：
    - `heading_1`, `heading_2`, `heading_3`
    - `paragraph`
    - `code_block`
    - `list_item`
    - `table`
    - `image_region`
- **输出**：按阅读顺序（Top-to-Bottom, Left-to-Right）排序的区块元数据序列。

### FR-102: 多语言密集文本提取 (OCR & Text Parsing)
- **处理逻辑**：
  - 针对每一个非图像区块，调用推理引擎提取 UTF-8 文本内容；
  - **断行自愈算法 (De-hyphenation)**：
    - 识别英文行末单词连字符 `-`，自动合并为完整单词；
    - 中文行末换行若无显式标点符号（如逗号、句号、分号），自动剔除换行符合并为一个连续自然语义段落，防止 Markdown 渲染出现恼人的碎片断行。

### FR-103: DocAST v1.0 抽象语法树构造 (DocAST Construction)
- **处理逻辑**：
  - 将所有提取并清洗后的区块，封装为与格式无关的内存 JSON 结构（DocAST）；
  - 保留原始边界框坐标与全局时序索引，为后续版本的双模态坐标溯源奠定底层数据契约。

### FR-104: 标准 Markdown (GFM) 编译器
- **处理逻辑**：
  - 遍历 DocAST，根据节点类型执行 Markdown 序列化映射：
    - `heading_N` -> `#` 数量前缀；
    - `paragraph` -> 双换行自然段落；
    - `code_block` -> 带有语言标识的 ````lang 代码块；
    - `list_item` -> `- ` 或 `1. ` 符号项；
- **输出**：生成 UTF-8 编码的 `.md` 文本文件，以及提取的内嵌图片附件目录。

---

## 4. 核心数据契约：DocAST v1.0 JSON Schema

系统各模块间解耦流转的核心数据结构必须严格遵守以下规范：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DocAST_v1",
  "type": "object",
  "required": ["doc_id", "source_metadata", "blocks"],
  "properties": {
    "doc_id": { "type": "string", "description": "文档唯一UUID" },
    "version": { "type": "string", "enum": ["1.0"] },
    "source_metadata": {
      "type": "object",
      "required": ["file_name", "width", "height"],
      "properties": {
        "file_name": { "type": "string" },
        "file_hash": { "type": "string" },
        "width": { "type": "integer" },
        "height": { "type": "integer" }
      }
    },
    "blocks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["block_id", "type", "bbox", "content"],
        "properties": {
          "block_id": { "type": "string" },
          "type": {
            "type": "string",
            "enum": ["heading_1", "heading_2", "heading_3", "paragraph", "code_block", "list_item", "table", "image_region"]
          },
          "bbox": {
            "type": "array",
            "items": { "type": "integer" },
            "minItems": 4,
            "maxItems": 4,
            "description": "[ymin, xmin, ymax, xmax] 归一化千分比坐标"
          },
          "content": { "type": "string" },
          "language": { "type": "string", "description": "针对code_block的代码语言识别结果" },
          "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
        }
      }
    }
  }
}
```

---

## 5. 典型异常与错误码定义

| 错误码 | 异常分类 | 触发条件 | 系统处置策略 |
| :--- | :--- | :--- | :--- |
| **ERR-IMG-001** | 文件损坏或非法格式 | 解码器无法解析二进制流 | 立即中断该图处理，记录错误日志，返回具体字节偏移错误 |
| **ERR-IMG-002** | 分辨率不足 | 宽高任一边小于 400px | 终止处理，提示“图像清晰度过低无法稳定解析” |
| **ERR-IMG-003** | 画面内容过曝/全黑 | 图像灰度均值 $> 250$ 或 $< 5$ | 判定为空白或无效帧，跳过并记录告警 |
| **ERR-OCR-001** | 推理显存不足 (OOM) | 显卡显存溢出 | 自动熔断降级至 CPU 串行推理队列，抛出低速告警 |
