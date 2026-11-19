"""图像摄入、EXIF显式矩阵归一化、频域摩尔纹剥离、高光死区探测与逆矩阵守恒模块。"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class PreprocessError(RuntimeError):
    """预处理流水线强校验异常基类。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PreprocessConfig:
    """图像预处理参数配置契约。"""

    min_dimension: int = 400
    max_dimension: int = 4096
    max_deskew_angle: float = 15.0
    enable_fft_notch: bool = True
    enable_illumination_norm: bool = True
    sharpness_threshold: float = 25.0
    glare_saturation_threshold: int = 253
    glare_min_area_px: int = 64


@dataclass
class PreprocessOutput:
    """预处理输出张量与逆变换坐标元数据。"""

    deskewed_rgb: np.ndarray
    enhanced_rgb: np.ndarray
    source_sha256: str
    raw_dimensions: Tuple[int, int, int]
    processed_dimensions: Tuple[int, int]
    exif_orientation: int
    skew_angle_deg: float
    scale_factor: float
    forward_matrix: np.ndarray
    inverse_matrix: np.ndarray
    glare_deadzone_bboxes: List[List[int]]
    glare_percentage: float
    laplacian_sharpness_score: float
    warnings: List[str] = field(default_factory=list)


def validate_image_magic(raw_bytes: bytes) -> str:
    """校验常见图像文件魔数，拒绝无效或损坏二进制流（ERR-PRE-001）。"""
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "webp"
    if raw_bytes.startswith(b"BM"):
        return "bmp"
    raise PreprocessError("ERR-PRE-001", "Unsupported or corrupted image binary magic header.")


def build_exif_matrix(orientation: int, width: int, height: int) -> Tuple[np.ndarray, Tuple[int, int]]:
    """根据 EXIF 0x0112 姿态标签构造显式 3x3 齐次变换矩阵及输出画布尺寸。"""
    if orientation == 1 or orientation not in {2, 3, 4, 5, 6, 7, 8}:
        return np.eye(3, dtype=np.float64), (width, height)
    if orientation == 2:
        mat = np.array([[-1.0, 0.0, width - 1.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        return mat, (width, height)
    if orientation == 3:
        mat = np.array([[-1.0, 0.0, width - 1.0], [0.0, -1.0, height - 1.0], [0.0, 0.0, 1.0]])
        return mat, (width, height)
    if orientation == 4:
        mat = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, height - 1.0], [0.0, 0.0, 1.0]])
        return mat, (width, height)
    if orientation == 5:
        mat = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        return mat, (height, width)
    if orientation == 6:
        mat = np.array([[0.0, -1.0, height - 1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        return mat, (height, width)
    if orientation == 7:
        mat = np.array([[0.0, -1.0, height - 1.0], [-1.0, 0.0, width - 1.0], [0.0, 0.0, 1.0]])
        return mat, (height, width)
    # orientation == 8 (90 CCW / 270 CW)
    mat = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, width - 1.0], [0.0, 0.0, 1.0]])
    return mat, (height, width)


def estimate_skew_angle_deg(gray: np.ndarray) -> float:
    """基于 Canny + 概率霍夫线段长度加权直方图估计主文本行偏转角（度）。"""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_line_len = max(40, int(min(gray.shape[:2]) * 0.08))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720.0, threshold=60, minLineLength=min_line_len, maxLineGap=12)
    if lines is None or len(lines) == 0:
        return 0.0

    angles: List[float] = []
    weights: List[float] = []
    for line in lines[:, 0, :]:
        x1, y1, x2, y2 = line
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = float(np.hypot(dx, dy))
        if length < 1e-3:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        if angle > 45.0:
            angle -= 90.0
        elif angle < -45.0:
            angle += 90.0
        if abs(angle) <= 25.0:
            angles.append(angle)
            weights.append(length)

    if not angles:
        return 0.0

    hist, bin_edges = np.histogram(angles, bins=100, range=(-25.0, 25.0), weights=weights)
    peak_idx = int(np.argmax(hist))
    return float(0.5 * (bin_edges[peak_idx] + bin_edges[peak_idx + 1]))


def remove_moire_fft_notch(
    luma: np.ndarray,
    dc_radius_ratio: float = 0.05,
    axis_protect_px: int = 8,
    peak_ratio: float = 1.45,
    notch_sigma: float = 5.0,
) -> np.ndarray:
    """2D FFT 定向保护性陷波：保护直流区与水平/垂直文字笔画轴，抑制周期摩尔纹尖峰。"""
    h, w = luma.shape
    f_shift = np.fft.fftshift(np.fft.fft2(luma.astype(np.float32)))
    mag = np.log1p(np.abs(f_shift))
    mag_u8 = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    med_u8 = cv2.medianBlur(mag_u8, 9)
    ratio = mag_u8.astype(np.float32) / np.maximum(med_u8.astype(np.float32), 1.0)

    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    dist_dc = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_dc = min(h, w) * dc_radius_ratio

    protected = (dist_dc < r_dc) | (np.abs(yy - cy) <= axis_protect_px) | (np.abs(xx - cx) <= axis_protect_px)
    peak_mask = (ratio > peak_ratio) & (~protected)

    ys, xs = np.where(peak_mask)
    if len(ys) == 0:
        return luma

    # 限制最多选取能量最高的 24 对尖峰，防止过度衰减
    scores = ratio[ys, xs]
    top_k = np.argsort(scores)[::-1][:24]
    notch = np.ones((h, w), dtype=np.float32)
    denom = 2.0 * (notch_sigma ** 2)
    for idx in top_k:
        py, px = int(ys[idx]), int(xs[idx])
        notch *= 1.0 - np.exp(-(((yy - py) ** 2 + (xx - px) ** 2) / denom))

    cleaned = np.fft.ifft2(np.fft.ifftshift(f_shift * notch)).real
    return np.clip(cleaned, 0, 255).astype(np.uint8)


def normalize_illumination_division(luma: np.ndarray, kernel_size: int = 35) -> np.ndarray:
    """基于大核形态学背景估计的除法归一化，恢复半透明反光光晕下的小字对比度。"""
    if float(np.median(luma)) < 127.0:
        # 深色 IDE/终端背景跳过亮底除法归一化，防止高亮文字背景扩张
        return luma
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    bg = cv2.morphologyEx(luma, cv2.MORPH_CLOSE, kernel)
    norm = (luma.astype(np.float32) / np.maximum(bg.astype(np.float32), 1.0)) * 255.0
    return np.clip(norm, 0, 255).astype(np.uint8)


def detect_glare_deadzone(
    rgb: np.ndarray,
    sat_threshold: int = 253,
    min_area_px: int = 64,
) -> Tuple[List[List[int]], float]:
    """检测通道截断的死白过曝区域，输出边界框列表 [ymin, xmin, ymax, xmax] 与面积占比。"""
    saturated = np.all(rgb >= sat_threshold, axis=2).astype(np.uint8)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(saturated, connectivity=8)
    total_pixels = float(rgb.shape[0] * rgb.shape[1])
    deadzone_bboxes: List[List[int]] = []
    glare_area = 0

    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        if int(area) >= min_area_px:
            deadzone_bboxes.append([int(y), int(x), int(y + h), int(x + w)])
            glare_area += int(area)

    return deadzone_bboxes, float(glare_area / max(total_pixels, 1.0))


def project_points_to_raw(points_xy: np.ndarray, inverse_matrix: np.ndarray) -> np.ndarray:
    """使用 3x3 逆变换矩阵将校平图坐标批量反投回原始未变形底片像素坐标。"""
    pts = np.asarray(points_xy, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("points_xy must have shape (N, 2)")
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    hom = np.hstack([pts, ones])
    mapped = (inverse_matrix @ hom.T).T
    w = np.where(np.abs(mapped[:, 2:3]) < 1e-12, 1.0, mapped[:, 2:3])
    return mapped[:, :2] / w


class ImagePreprocessor:
    """PRD-01 图像摄入、EXIF 归一化、几何校平、退化抑制与逆矩阵守恒处理器。"""

    def __init__(self, config: Optional[PreprocessConfig] = None) -> None:
        self.config = config or PreprocessConfig()

    def process(self, input_source: bytes | str | Path) -> PreprocessOutput:
        """执行完整图像清洗流水线并沉淀全链路 3x3 逆单应性矩阵。"""
        if isinstance(input_source, (str, Path)):
            raw_bytes = Path(input_source).read_bytes()
        else:
            raw_bytes = input_source

        validate_image_magic(raw_bytes)
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        pil_img = Image.open(io.BytesIO(raw_bytes))
        exif = pil_img.getexif()
        orientation = int(exif.get(0x0112, 1)) if exif else 1
        rgb_raw = np.asarray(pil_img.convert("RGB"))
        h0, w0, c0 = rgb_raw.shape

        if min(w0, h0) < self.config.min_dimension:
            raise PreprocessError(
                "ERR-PRE-002",
                f"Image dimension ({w0}x{h0}) is below minimum {self.config.min_dimension}px.",
            )

        warnings: List[str] = []

        # 1. 显式 EXIF 矩阵旋转
        r_exif, (w_rot, h_rot) = build_exif_matrix(orientation, w0, h0)
        rgb_rot = cv2.warpAffine(rgb_raw, r_exif[:2, :], (w_rot, h_rot), flags=cv2.INTER_NEAREST)

        # 2. 长边超限双三次降采样
        max_side = max(w_rot, h_rot)
        if max_side > self.config.max_dimension:
            scale_factor = self.config.max_dimension / float(max_side)
            w_scaled = int(round(w_rot * scale_factor))
            h_scaled = int(round(h_rot * scale_factor))
            m_scale = np.array([[scale_factor, 0.0, 0.0], [0.0, scale_factor, 0.0], [0.0, 0.0, 1.0]])
            rgb_scaled = cv2.resize(rgb_rot, (w_scaled, h_scaled), interpolation=cv2.INTER_CUBIC)
        else:
            scale_factor = 1.0
            w_scaled, h_scaled = w_rot, h_rot
            m_scale = np.eye(3, dtype=np.float64)
            rgb_scaled = rgb_rot

        # 3. 霍夫倾斜角检测与门禁校平
        gray_scaled = cv2.cvtColor(rgb_scaled, cv2.COLOR_RGB2GRAY)
        skew_angle = estimate_skew_angle_deg(gray_scaled)
        if 0.15 <= abs(skew_angle) <= self.config.max_deskew_angle:
            center = (w_scaled / 2.0, h_scaled / 2.0)
            m_2x3 = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
            m_skew = np.vstack([m_2x3, [0.0, 0.0, 1.0]])
            deskewed_rgb = cv2.warpAffine(
                rgb_scaled,
                m_2x3,
                (w_scaled, h_scaled),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
        else:
            if abs(skew_angle) > self.config.max_deskew_angle:
                warnings.append(f"WARN_SKEW_EXCEEDED: detected {skew_angle:.2f} deg > {self.config.max_deskew_angle}")
                skew_angle = 0.0
            m_skew = np.eye(3, dtype=np.float64)
            deskewed_rgb = rgb_scaled.copy()

        # 4. 复合全链路正/逆矩阵
        forward_matrix = m_skew @ m_scale @ r_exif
        inverse_matrix = np.linalg.inv(forward_matrix)

        # 5. 高光死区检测与画质评估
        glare_bboxes, glare_pct = detect_glare_deadzone(
            deskewed_rgb,
            sat_threshold=self.config.glare_saturation_threshold,
            min_area_px=self.config.glare_min_area_px,
        )
        gray_deskewed = cv2.cvtColor(deskewed_rgb, cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(gray_deskewed, cv2.CV_64F).var())
        if sharpness < self.config.sharpness_threshold:
            warnings.append(f"Quality_Severely_Blurred: laplacian={sharpness:.2f}")

        # 6. 推理增强分支（保留 deskewed_rgb 原样用于插图裁切与溯源核验）
        lab = cv2.cvtColor(deskewed_rgb, cv2.COLOR_RGB2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        if self.config.enable_fft_notch:
            l_chan = remove_moire_fft_notch(l_chan)
        if self.config.enable_illumination_norm:
            l_chan = normalize_illumination_division(l_chan)
        enhanced_rgb = cv2.cvtColor(cv2.merge([l_chan, a_chan, b_chan]), cv2.COLOR_LAB2RGB)

        return PreprocessOutput(
            deskewed_rgb=deskewed_rgb,
            enhanced_rgb=enhanced_rgb,
            source_sha256=source_sha256,
            raw_dimensions=(w0, h0, c0),
            processed_dimensions=(w_scaled, h_scaled),
            exif_orientation=orientation,
            skew_angle_deg=skew_angle,
            scale_factor=scale_factor,
            forward_matrix=forward_matrix,
            inverse_matrix=inverse_matrix,
            glare_deadzone_bboxes=glare_bboxes,
            glare_percentage=glare_pct,
            laplacian_sharpness_score=sharpness,
            warnings=warnings,
        )
