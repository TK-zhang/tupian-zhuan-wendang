"""核心 DocAST 内存数据模型、状态机契约与双模态溯源索引定义。"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ASTState(str, Enum):
    """DocAST 生命周期状态机枚举。"""

    CREATED = "CREATED"
    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    RECTIFIED = "RECTIFIED"
    COMPILED = "COMPILED"
    FAILED = "FAILED"


class NodeType(str, Enum):
    """DocNode 多态节点类型枚举。"""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE_BLOCK = "code_block"
    TABLE = "table"
    IMAGE = "image"
    LIST = "list"


class ProvenanceRef(BaseModel):
    """亚像素级双模态来源溯源坐标契约。"""

    source_file_name: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    clean_bbox_px: List[int] = Field(min_length=4, max_length=4)
    raw_polygon_px: List[List[float]] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)


class BaseDocNode(BaseModel):
    """DocNode 公共基类。"""

    node_id: str
    node_type: NodeType
    bbox_normalized: List[int] = Field(min_length=4, max_length=4)
    source_evidence: ProvenanceRef


class HeadingNode(BaseDocNode):
    """标题节点。"""

    node_type: Literal[NodeType.HEADING] = NodeType.HEADING
    level: int = Field(ge=1, le=6)
    title_text: str
    anchor_id: str


class ParagraphNode(BaseDocNode):
    """自然文本段落节点。"""

    node_type: Literal[NodeType.PARAGRAPH] = NodeType.PARAGRAPH
    text: str
    has_low_confidence: bool = False


class CodeBlockNode(BaseDocNode):
    """代码块节点（强制保留等宽缩进与静态语法校验标记）。"""

    node_type: Literal[NodeType.CODE_BLOCK] = NodeType.CODE_BLOCK
    code_content: str
    language: str = "text"
    syntax_verified: bool = False


class GridCell(BaseModel):
    """二维表格单元格拓扑描述对象。"""

    row: int = Field(ge=0)
    col: int = Field(ge=0)
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)
    text: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[ProvenanceRef] = None


class TableNode(BaseDocNode):
    """二维表格节点，承载规范化后的行列拓扑及单元格。"""

    node_type: Literal[NodeType.TABLE] = NodeType.TABLE
    rows: int = Field(ge=1)
    cols: int = Field(ge=1)
    cells: List[GridCell] = Field(default_factory=list)


class ImageNode(BaseDocNode):
    """插图与拓扑图切片节点。"""

    node_type: Literal[NodeType.IMAGE] = NodeType.IMAGE
    asset_rel_path: str
    caption: str = ""
    aspect_ratio: float = Field(default=1.0, gt=0.0)


class ListNode(BaseDocNode):
    """有序或无序列表节点。"""

    node_type: Literal[NodeType.LIST] = NodeType.LIST
    is_ordered: bool = False
    items: List[str] = Field(default_factory=list)


DocNode = Annotated[
    Union[
        HeadingNode,
        ParagraphNode,
        CodeBlockNode,
        TableNode,
        ImageNode,
        ListNode,
    ],
    Field(discriminator="node_type"),
]


class ReviewTicket(BaseModel):
    """非阻塞待复核工单数据结构。"""

    ticket_id: str
    node_id: str
    ticket_type: Literal[
        "LOW_CONFIDENCE",
        "GLARE_OCCLUDED",
        "TEMPORAL_CONFLICT",
        "SCROLL_GAP_DETECTED",
        "SYNTAX_ERROR",
        "TABLE_TOPOLOGY_AMBIGUITY",
    ]
    extracted_value: str
    candidate_value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ProvenanceRef
    resolved: bool = False


class ASTStateTransitionError(RuntimeError):
    """非法 AST 状态跃迁异常（ERR-AST-003）。"""

    def __init__(self, message: str) -> None:
        super().__init__(f"ERR-AST-003: {message}")


def _is_empty_node(node: DocNode) -> bool:
    """判定节点是否为空内容死节点。"""
    if isinstance(node, HeadingNode):
        return not node.title_text.strip()
    if isinstance(node, ParagraphNode):
        return not node.text.strip()
    if isinstance(node, CodeBlockNode):
        return not node.code_content.strip()
    if isinstance(node, TableNode):
        return len(node.cells) == 0
    if isinstance(node, ImageNode):
        return not node.asset_rel_path.strip()
    if isinstance(node, ListNode):
        return len([item for item in node.items if item.strip()]) == 0
    return False


class DocAST(BaseModel):
    """系统核心数据总线：强类型文档抽象语法树与状态机。"""

    doc_id: str
    schema_version: str = "1.0.0"
    status: ASTState = ASTState.CREATED
    metadata: Dict[str, Any] = Field(default_factory=dict)
    nodes: List[DocNode] = Field(default_factory=list)
    review_tickets: List[ReviewTicket] = Field(default_factory=list)

    def append_node(self, node: DocNode) -> None:
        """在文档末尾追加节点，自动消除 ID 碰撞（ERR-AST-002）。"""
        existing_ids = {n.node_id for n in self.nodes}
        if node.node_id in existing_ids:
            node.node_id = f"{node.node_id}_{uuid.uuid4().hex[:6]}"
        self.nodes.append(node)
        if self.status == ASTState.CREATED:
            self.status = ASTState.INGESTED

    def get_node_by_id(self, node_id: str) -> Optional[DocNode]:
        """按节点 ID 检索节点。"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def traverse(self, visitor_fn: Callable[[DocNode], None]) -> None:
        """按阅读序深度遍历全部节点。"""
        for node in self.nodes:
            visitor_fn(node)

    def filter_by_type(self, node_type: NodeType) -> List[DocNode]:
        """按类型过滤返回节点列表。"""
        return [n for n in self.nodes if n.node_type == node_type]

    def validate_invariants(self) -> bool:
        """执行死节点剪枝、ID 唯一性校验及标题层级连续性修正，状态跃迁至 VALIDATED。"""
        cleaned: List[DocNode] = []
        seen_ids: set[str] = set()
        last_heading_level = 0

        for node in self.nodes:
            if _is_empty_node(node):
                continue
            if node.node_id in seen_ids:
                node.node_id = f"{node.node_id}_{uuid.uuid4().hex[:6]}"
            seen_ids.add(node.node_id)

            if isinstance(node, HeadingNode):
                if last_heading_level == 0 and node.level > 1:
                    node.level = 1
                elif node.level > last_heading_level + 1:
                    node.level = last_heading_level + 1
                last_heading_level = node.level

            cleaned.append(node)

        self.nodes = cleaned
        self.status = ASTState.VALIDATED
        return True

    def assert_ready_for_compile(self) -> None:
        """状态门禁检查：仅 VALIDATED / RECTIFIED 状态允许触发编译器。"""
        if self.status not in {ASTState.VALIDATED, ASTState.RECTIFIED}:
            raise ASTStateTransitionError(
                f"Cannot compile DocAST in state '{self.status.value}'; call validate_invariants() first."
            )

    def to_json(self, indent: int = 2) -> str:
        """无损序列化为标准 JSON 字符串。"""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "DocAST":
        """从 JSON 字符串无损重建 DocAST 对象。"""
        return cls.model_validate_json(json_str)
