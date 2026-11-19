# PR 交付计划与首批核心函数签名清单 (PR Plan & Core Function Signatures)

> **目标**：严格按小颗粒度、可独立单测与基准门禁验收的原则拆分首批 4 个核心 PR，优先交付基础设施与确定性不变量核心函数。

---

## 1. 首批 PR 拆分矩阵

| PR 编号 | 关联阶段 | 模块与文件 | 核心交付物与准出断言 |
| :--- | :--- | :--- | :--- |
| **PR-01** | `MVP-0` | `datasets/gold_samples/` + `src/doc_reconstruct/models.py` | 12 组 Gold Samples 测试集 + 强类型 `DocAST` 多态节点、状态机跃迁守卫（`ERR-AST-003`）及 `to_json`/`from_json` 零损耗往返测试 |
| **PR-02** | `MVP-0` | `src/doc_reconstruct/preprocess.py` | `ImagePreprocessor.process()` + 显式 EXIF $3\times 3$ 矩阵 + 2D FFT 保护性陷波 + 光照除法归一化 + `detect_glare_deadzone()` + `project_points_to_raw()`（误差 $< 1.0\text{ px}$） |
| **PR-03** | `MVP-1` | `src/doc_reconstruct/table_solver.py` | `OccupancyGridSolver.solve()`：$M\times N$ 物理占用矩阵碰撞裁剪、同步 `gridSpan` + `vMerge` 发射、行级宽度与列数硬断言（兼容 Office 2007+ / WPS） |
| **PR-04** | `MVP-2` | `src/doc_reconstruct/scroll_stitch.py` | `mark_clipped_edge_lines()` + `compute_scroll_seam_partition()`：视口腰斩脏行屏蔽与唯一接缝超平面 $Y_{\text{seam}}$ 不漏不重划分 |

---

## 2. 首批关键核心函数签名

### 2.1 预处理与逆矩阵守恒入口（[preprocess.py](file:///c:/Users/zhangtengkuan/Desktop/自己的项目/图片转文档/src/doc_reconstruct/preprocess.py)）
```python
class ImagePreprocessor:
    def __init__(self, config: Optional[PreprocessConfig] = None) -> None: ...
    def process(self, input_source: bytes | str | Path) -> PreprocessOutput: ...

def build_exif_matrix(orientation: int, width: int, height: int) -> Tuple[np.ndarray, Tuple[int, int]]: ...
def remove_moire_fft_notch(luma: np.ndarray, dc_radius_ratio: float = 0.05, axis_protect_px: int = 8) -> np.ndarray: ...
def detect_glare_deadzone(rgb: np.ndarray, sat_threshold: int = 253, min_area_px: int = 64) -> Tuple[List[List[int]], float]: ...
def project_points_to_raw(points_xy: np.ndarray, inverse_matrix: np.ndarray) -> np.ndarray: ...
```

### 2.2 OpenXML 表格网格不变量求解器（[table_solver.py](file:///c:/Users/zhangtengkuan/Desktop/自己的项目/图片转文档/src/doc_reconstruct/table_solver.py)）
```python
class OccupancyGridSolver:
    def __init__(self, rows: int, cols: int, col_widths_dxa: Optional[List[int]] = None) -> None: ...
    def solve(self, raw_cells: List[GridCell]) -> Tuple[List[List[OpenXMLCellEmit]], List[str]]: ...
```

### 2.3 滚动切片接缝划分器（[scroll_stitch.py](file:///c:/Users/zhangtengkuan/Desktop/自己的项目/图片转文档/src/doc_reconstruct/scroll_stitch.py)）
```python
def mark_clipped_edge_lines(lines: List[OCRLineBox], image_height: int) -> List[OCRLineBox]: ...
def compute_scroll_seam_partition(
    frame_k_lines: List[OCRLineBox],
    frame_next_lines: List[OCRLineBox],
    frame_k_height: int,
) -> ScrollSeamResult: ...
```
