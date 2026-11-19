"""OpenXML Transitional 表格拓扑物理占用矩阵求解器（保证 gridSpan / vMerge 零错位）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

from .models import GridCell


@dataclass(frozen=True)
class OpenXMLCellEmit:
    """经过物理占用矩阵验证后准备发射的 OpenXML 单元格指令。"""

    row: int
    col: int
    grid_span: int
    v_merge: Optional[Literal["restart", "continue"]]
    width_dxa: int
    text: str


@dataclass
class OccupancySlot:
    """M x N 物理占用网格单格状态。"""

    kind: Literal["EMPTY", "ORIGIN", "H_COVERED", "V_COVERED"]
    origin_cell: Optional[GridCell] = None


class OccupancyGridSolver:
    """确定性表格二维网格碰撞消解与 OpenXML Transitional 行列发射求解器。"""

    def __init__(self, rows: int, cols: int, col_widths_dxa: Optional[List[int]] = None) -> None:
        if rows <= 0 or cols <= 0:
            raise ValueError("Table rows and cols must be positive integers.")
        self.rows = rows
        self.cols = cols
        if col_widths_dxa is not None:
            if len(col_widths_dxa) != cols:
                raise ValueError("col_widths_dxa length must match cols.")
            self.col_widths_dxa = list(col_widths_dxa)
        else:
            base = 9000 // cols
            self.col_widths_dxa = [base] * cols

    def solve(self, raw_cells: List[GridCell]) -> Tuple[List[List[OpenXMLCellEmit]], List[str]]:
        """灌注候选合并单元格，消解越界/碰撞并输出严格满足行宽守恒的 OpenXML 发射指令。"""
        occ: List[List[OccupancySlot]] = [
            [OccupancySlot(kind="EMPTY") for _ in range(self.cols)] for _ in range(self.rows)
        ]
        warnings: List[str] = []

        sorted_cells = sorted(raw_cells, key=lambda c: (c.row, c.col))
        for cell in sorted_cells:
            if cell.row >= self.rows or cell.col >= self.cols:
                warnings.append(f"Clamped out-of-bounds cell at ({cell.row}, {cell.col}).")
                continue

            if occ[cell.row][cell.col].kind != "EMPTY":
                warnings.append(f"Skipped colliding cell at ({cell.row}, {cell.col}): '{cell.text[:20]}'.")
                continue

            max_rs = min(cell.rowspan, self.rows - cell.row)
            max_cs = min(cell.colspan, self.cols - cell.col)

            # 按先行后列裁剪避免与已有单元格发生空间重叠
            valid_cs = 1
            while valid_cs < max_cs and occ[cell.row][cell.col + valid_cs].kind == "EMPTY":
                valid_cs += 1

            valid_rs = 1
            while valid_rs < max_rs:
                row_free = all(occ[cell.row + valid_rs][cell.col + dc].kind == "EMPTY" for dc in range(valid_cs))
                if not row_free:
                    break
                valid_rs += 1

            if valid_rs != cell.rowspan or valid_cs != cell.colspan:
                warnings.append(
                    f"Clipped span at ({cell.row}, {cell.col}) from ({cell.rowspan},{cell.colspan}) to ({valid_rs},{valid_cs})."
                )

            normalized = GridCell(
                row=cell.row,
                col=cell.col,
                rowspan=valid_rs,
                colspan=valid_cs,
                text=cell.text,
                confidence=cell.confidence,
                provenance=cell.provenance,
            )

            for dr in range(valid_rs):
                for dc in range(valid_cs):
                    if dr == 0 and dc == 0:
                        occ[cell.row][cell.col] = OccupancySlot(kind="ORIGIN", origin_cell=normalized)
                    elif dr == 0:
                        occ[cell.row][cell.col + dc] = OccupancySlot(kind="H_COVERED", origin_cell=normalized)
                    else:
                        occ[cell.row + dr][cell.col + dc] = OccupancySlot(kind="V_COVERED", origin_cell=normalized)

        # 填补剩余孔洞为 1x1 空单元格
        for r in range(self.rows):
            for c in range(self.cols):
                if occ[r][c].kind == "EMPTY":
                    occ[r][c] = OccupancySlot(
                        kind="ORIGIN",
                        origin_cell=GridCell(row=r, col=c, rowspan=1, colspan=1, text=""),
                    )

        # 按行发射严格同步 gridSpan 与 vMerge 的单元格序列
        emitted_rows: List[List[OpenXMLCellEmit]] = []
        total_grid_width = sum(self.col_widths_dxa)

        for r in range(self.rows):
            row_emits: List[OpenXMLCellEmit] = []
            c = 0
            while c < self.cols:
                slot = occ[r][c]
                origin = slot.origin_cell
                assert origin is not None
                span = origin.colspan
                width_dxa = sum(self.col_widths_dxa[c : c + span])

                if slot.kind == "ORIGIN":
                    v_merge: Optional[Literal["restart", "continue"]] = "restart" if origin.rowspan > 1 else None
                    row_emits.append(
                        OpenXMLCellEmit(
                            row=r,
                            col=c,
                            grid_span=span,
                            v_merge=v_merge,
                            width_dxa=width_dxa,
                            text=origin.text,
                        )
                    )
                    c += span
                elif slot.kind == "V_COVERED":
                    # V_COVERED 的首列必须同步发射相同 gridSpan 的空续接单元格
                    row_emits.append(
                        OpenXMLCellEmit(
                            row=r,
                            col=c,
                            grid_span=span,
                            v_merge="continue",
                            width_dxa=width_dxa,
                            text="",
                        )
                    )
                    c += span
                else:
                    raise AssertionError(f"Unexpected slot state {slot.kind} reached at ({r}, {c}).")

            # 行级数学不变量硬断言
            assert sum(e.grid_span for e in row_emits) == self.cols
            assert sum(e.width_dxa for e in row_emits) == total_grid_width
            emitted_rows.append(row_emits)

        return emitted_rows, warnings
