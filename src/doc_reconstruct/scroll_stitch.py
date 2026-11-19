"""跨多图与长录屏滚动切片拼接：边缘截断脏行屏蔽与唯一接缝超平面划分契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class OCRLineBox:
    """单行 OCR 文本与绝对像素外接框。"""

    line_index: int
    text: str
    ymin: int
    xmin: int
    ymax: int
    xmax: int
    confidence: float
    is_clipped_edge: bool = False

    @property
    def height(self) -> int:
        return max(0, self.ymax - self.ymin)

    @property
    def center_y(self) -> float:
        return 0.5 * (self.ymin + self.ymax)


@dataclass(frozen=True)
class ScrollSeamResult:
    """两帧滚动对齐与唯一接缝切分结果。"""

    delta_y_px: float
    seam_cut_y_frame_k: float
    has_scroll_gap: bool
    frame_k_kept_indices: List[int]
    frame_next_kept_indices: List[int]


def mark_clipped_edge_lines(
    lines: List[OCRLineBox],
    image_height: int,
    edge_margin_px: int = 12,
    height_ratio_threshold: float = 0.78,
) -> List[OCRLineBox]:
    """检测视口上下边缘被横截面腰斩的脏行，禁止其参与 LCS 锚点对齐。"""
    if not lines:
        return []
    heights = sorted(line.height for line in lines if line.height > 0)
    median_h = heights[len(heights) // 2] if heights else 20

    marked: List[OCRLineBox] = []
    for line in lines:
        near_edge = line.ymin <= edge_margin_px or line.ymax >= (image_height - edge_margin_px)
        clipped = near_edge and (line.height < median_h * height_ratio_threshold)
        marked.append(
            OCRLineBox(
                line_index=line.line_index,
                text=line.text,
                ymin=line.ymin,
                xmin=line.xmin,
                ymax=line.ymax,
                xmax=line.xmax,
                confidence=line.confidence,
                is_clipped_edge=clipped,
            )
        )
    return marked


def compute_scroll_seam_partition(
    frame_k_lines: List[OCRLineBox],
    frame_next_lines: List[OCRLineBox],
    frame_k_height: int,
    edge_margin_px: int = 12,
) -> ScrollSeamResult:
    """利用完整内部锚点行求刚性滚动位移 delta_y，并在空白间隙建立唯一接缝超平面 Y_seam。"""
    k_marked = mark_clipped_edge_lines(frame_k_lines, frame_k_height, edge_margin_px)
    n_marked = mark_clipped_edge_lines(frame_next_lines, frame_k_height, edge_margin_px)

    k_clean = [ln for ln in k_marked if not ln.is_clipped_edge and ln.text.strip()]
    n_clean = [ln for ln in n_marked if not ln.is_clipped_edge and ln.text.strip()]

    n_lookup = {ln.text.strip(): ln for ln in n_clean}
    matched_pairs: List[Tuple[OCRLineBox, OCRLineBox]] = []
    for ln_k in k_clean:
        key = ln_k.text.strip()
        if key in n_lookup:
            matched_pairs.append((ln_k, n_lookup[key]))

    if len(matched_pairs) < 2:
        return ScrollSeamResult(
            delta_y_px=0.0,
            seam_cut_y_frame_k=float(frame_k_height),
            has_scroll_gap=True,
            frame_k_kept_indices=[ln.line_index for ln in k_clean],
            frame_next_kept_indices=[ln.line_index for ln in n_clean],
        )

    deltas = [ln_k.center_y - ln_n.center_y for ln_k, ln_n in matched_pairs]
    delta_y = sum(deltas) / len(deltas)

    # 选择第一对锚点行正上方的行间空白中线作为唯一接缝超平面 Y_seam
    first_anchor_k = matched_pairs[0][0]
    seam_y = float(first_anchor_k.ymin) - 2.0

    k_kept = [ln.line_index for ln in k_clean if ln.center_y < seam_y]
    n_kept = [ln.line_index for ln in n_clean if (ln.center_y + delta_y) >= seam_y]

    return ScrollSeamResult(
        delta_y_px=delta_y,
        seam_cut_y_frame_k=seam_y,
        has_scroll_gap=False,
        frame_k_kept_indices=k_kept,
        frame_next_kept_indices=n_kept,
    )
