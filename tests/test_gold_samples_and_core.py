"""Gold Samples 数据集完整性、几何逆矩阵守恒、OpenXML 网格求解与滚动接缝自动化测试。"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from doc_reconstruct.models import (  # noqa: E402
    ASTState,
    ASTStateTransitionError,
    DocAST,
    GridCell,
    HeadingNode,
    ParagraphNode,
    ProvenanceRef,
)
from doc_reconstruct.preprocess import (  # noqa: E402
    ImagePreprocessor,
    PreprocessError,
    project_points_to_raw,
)
from doc_reconstruct.scroll_stitch import (  # noqa: E402
    OCRLineBox,
    compute_scroll_seam_partition,
)
from doc_reconstruct.table_solver import OccupancyGridSolver  # noqa: E402

DATASET_DIR = ROOT_DIR / "datasets" / "gold_samples"


class TestGoldSamplesAndCore(unittest.TestCase):
    """验证 Gold Samples 基准数据集与首批核心模块真实可执行性。"""

    def test_01_gold_samples_manifest_and_sha256_integrity(self) -> None:
        manifest_path = DATASET_DIR / "manifest.json"
        self.assertTrue(manifest_path.exists(), "manifest.json must exist")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_samples"], 12)
        self.assertEqual(len(manifest["samples"]), 12)

        for entry in manifest["samples"]:
            img_path = DATASET_DIR / entry["rel_path"]
            ann_path = DATASET_DIR / entry["annotation_path"]
            self.assertTrue(img_path.exists(), f"Missing sample image: {img_path}")
            self.assertTrue(ann_path.exists(), f"Missing annotation: {ann_path}")

            actual_sha = hashlib.sha256(img_path.read_bytes()).hexdigest()
            self.assertEqual(actual_sha, entry["source_sha256"])

    def test_02_gs01_exif_orientation_6_and_inverse_projection(self) -> None:
        preprocessor = ImagePreprocessor()
        out = preprocessor.process(DATASET_DIR / "images" / "GS-01_exif_rot90_code.jpg")

        self.assertEqual(out.exif_orientation, 6)
        # 原始图横宽 1180x760 经逆时针90度存盘为 760x1180，EXIF=6 还原后应恢复为宽>高
        w_proc, h_proc = out.processed_dimensions
        self.assertGreater(w_proc, h_proc)

        identity_err = np.max(np.abs(out.inverse_matrix @ out.forward_matrix - np.eye(3)))
        self.assertLess(identity_err, 1e-6)

        pts_clean = np.array([[100.0, 50.0], [900.0, 600.0]], dtype=np.float64)
        pts_raw = project_points_to_raw(pts_clean, out.inverse_matrix)
        # 反投回原始 760x1180 坐标系应在图像边界内
        w_raw, h_raw, _ = out.raw_dimensions
        self.assertTrue(np.all((pts_raw[:, 0] >= 0) & (pts_raw[:, 0] < w_raw)))
        self.assertTrue(np.all((pts_raw[:, 1] >= 0) & (pts_raw[:, 1] < h_raw)))

    def test_03_gs02_skew_8_5_deg_recovery_and_roundtrip_error(self) -> None:
        preprocessor = ImagePreprocessor()
        out = preprocessor.process(DATASET_DIR / "images" / "GS-02_skew_8deg_config.png")

        self.assertGreater(abs(out.skew_angle_deg), 6.0)
        self.assertLess(abs(out.skew_angle_deg), 11.0)

        pts_clean = np.array([[200.0, 150.0], [950.0, 520.0]], dtype=np.float64)
        pts_raw = project_points_to_raw(pts_clean, out.inverse_matrix)
        pts_back = project_points_to_raw(pts_raw, out.forward_matrix)
        roundtrip_err = float(np.max(np.abs(pts_back - pts_clean)))
        self.assertLess(roundtrip_err, 1e-4)

    def test_04_gs04_glare_deadzone_detection_and_gs03_moire(self) -> None:
        preprocessor = ImagePreprocessor()
        out04 = preprocessor.process(DATASET_DIR / "images" / "GS-04_glare_deadzone_8pt_table.png")
        self.assertGreater(len(out04.glare_deadzone_bboxes), 0)
        self.assertGreater(out04.glare_percentage, 0.001)

        out03 = preprocessor.process(DATASET_DIR / "images" / "GS-03_perspective_moire_terminal.png")
        self.assertEqual(out03.enhanced_rgb.shape, out03.deskewed_rgb.shape)

    def test_05_preprocess_magic_and_dimension_guards(self) -> None:
        preprocessor = ImagePreprocessor()
        with self.assertRaises(PreprocessError) as ctx_magic:
            preprocessor.process(b"NOT_AN_IMAGE_STREAM_0000")
        self.assertEqual(ctx_magic.exception.code, "ERR-PRE-001")

    def test_06_docast_state_machine_and_lossless_roundtrip(self) -> None:
        prov = ProvenanceRef(
            source_file_name="GS-01_exif_rot90_code.jpg",
            source_sha256="a" * 64,
            clean_bbox_px=[10, 20, 100, 300],
            raw_polygon_px=[[20.0, 10.0], [300.0, 10.0], [300.0, 100.0], [20.0, 100.0]],
            confidence=0.96,
        )
        ast = DocAST(doc_id="doc_test_01")
        with self.assertRaises(ASTStateTransitionError):
            ast.assert_ready_for_compile()

        ast.append_node(
            HeadingNode(
                node_id="n1",
                bbox_normalized=[10, 20, 60, 400],
                source_evidence=prov,
                level=1,
                title_text="架构总览",
                anchor_id="sec-arch",
            )
        )
        # 故意写入越级 H4 标题与空死节点
        ast.append_node(
            HeadingNode(
                node_id="n2",
                bbox_normalized=[70, 20, 110, 400],
                source_evidence=prov,
                level=4,
                title_text="越级子节",
                anchor_id="sec-sub",
            )
        )
        ast.append_node(
            ParagraphNode(
                node_id="n_empty",
                bbox_normalized=[120, 20, 140, 200],
                source_evidence=prov,
                text="   ",
            )
        )
        self.assertTrue(ast.validate_invariants())
        self.assertEqual(ast.status, ASTState.VALIDATED)
        self.assertEqual(len(ast.nodes), 2)
        self.assertEqual(ast.nodes[1].level, 2)  # 越级 H4 平滑修正为 H2

        restored = DocAST.from_json(ast.to_json())
        self.assertEqual(restored, ast)

    def test_07_openxml_occupancy_grid_solver_syncs_gridspan_and_vmerge(self) -> None:
        solver = OccupancyGridSolver(rows=5, cols=4, col_widths_dxa=[2000, 2500, 2500, 2000])
        cells = [
            GridCell(row=0, col=0, rowspan=2, colspan=1, text="环境类型"),
            GridCell(row=0, col=1, rowspan=1, colspan=2, text="算力配置"),
            GridCell(row=0, col=3, rowspan=2, colspan=1, text="离线授权方式"),
            GridCell(row=1, col=1, rowspan=1, colspan=1, text="CPU架构"),
            GridCell(row=1, col=2, rowspan=1, colspan=1, text="加速卡"),
            # 构造一个同时跨行(rowspan=2)且跨列(colspan=2)的复合合并块
            GridCell(row=2, col=0, rowspan=2, colspan=2, text="政企信创复合节点"),
            # 故意制造碰撞单元格检验裁剪不崩溃
            GridCell(row=2, col=1, rowspan=1, colspan=1, text="非法重叠节点"),
        ]
        emitted_rows, warnings = solver.solve(cells)
        self.assertEqual(len(emitted_rows), 5)
        self.assertTrue(any("Skipped colliding cell" in w for w in warnings))

        # 验证第 3 行 (row=3) 中被 (row=2,col=0,rs=2,cs=2) 覆盖的续接单元格必须同步带 grid_span=2 与 v_merge="continue"
        row3_first = emitted_rows[3][0]
        self.assertEqual(row3_first.v_merge, "continue")
        self.assertEqual(row3_first.grid_span, 2)
        self.assertEqual(row3_first.width_dxa, 4500)

        for r in emitted_rows:
            self.assertEqual(sum(c.grid_span for c in r), 4)
            self.assertEqual(sum(c.width_dxa for c in r), 9000)

    def test_08_scroll_seam_partition_ignores_clipped_edge_lines(self) -> None:
        frame_k = [
            OCRLineBox(0, "PARAM_001 = 10.24.0.11", 20, 40, 44, 400, 0.98),
            OCRLineBox(1, "PARAM_002 = 10.24.0.12", 52, 40, 76, 400, 0.98),
            OCRLineBox(2, "PARAM_003 = 10.24.0.13", 84, 40, 108, 400, 0.98),
            # 底部视口边缘被腰斩半截（高度仅 9px）
            OCRLineBox(3, "PARAM_004_CORRUPT_?", 191, 40, 200, 400, 0.45),
        ]
        frame_next = [
            # 顶部视口边缘被腰斩半截
            OCRLineBox(0, "GARBAGE_TOP_HALF", 0, 40, 8, 400, 0.40),
            OCRLineBox(1, "PARAM_002 = 10.24.0.12", 16, 40, 40, 400, 0.98),
            OCRLineBox(2, "PARAM_003 = 10.24.0.13", 48, 40, 72, 400, 0.98),
            OCRLineBox(3, "PARAM_004 = 10.24.0.14", 80, 40, 104, 400, 0.98),
        ]
        res = compute_scroll_seam_partition(frame_k, frame_next, frame_k_height=200)
        self.assertFalse(res.has_scroll_gap)
        self.assertAlmostEqual(res.delta_y_px, 36.0, places=2)
        self.assertEqual(res.frame_k_kept_indices, [0])
        self.assertEqual(res.frame_next_kept_indices, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
