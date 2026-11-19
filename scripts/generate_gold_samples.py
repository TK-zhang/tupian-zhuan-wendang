"""生成 12 组屏摄退化 Gold Samples 基准测试集与精确 Ground Truth 标注。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "datasets" / "gold_samples"
IMG_DIR = OUT_DIR / "images"
ANN_DIR = OUT_DIR / "annotations"

FONT_CN = "C:/Windows/Fonts/msyh.ttc"
FONT_CN_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"
FONT_MONO_BOLD = "C:/Windows/Fonts/consolab.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def _new_canvas(w: int = 1280, h: int = 860, bg: Tuple[int, int, int] = (248, 250, 252)) -> Image.Image:
    return Image.new("RGB", (w, h), bg)


def _inject_rainbow_moire(img_rgb: np.ndarray, strength: float = 28.0) -> np.ndarray:
    """注入模拟显示器 RGB 子像素栅格与 CMOS 干涉产生的斜向彩虹摩尔纹。"""
    h, w, _ = img_rgb.shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    freq_1 = 0.27 * xx + 0.14 * yy
    freq_2 = -0.19 * xx + 0.23 * yy
    moire_r = strength * (0.65 * np.sin(freq_1) + 0.35 * np.cos(freq_2))
    moire_g = strength * (0.65 * np.sin(freq_1 + 1.05) + 0.35 * np.cos(freq_2 + 0.85))
    moire_b = strength * (0.65 * np.sin(freq_1 + 2.10) + 0.35 * np.cos(freq_2 + 1.70))
    out = img_rgb.astype(np.float32)
    out[:, :, 0] += moire_r
    out[:, :, 1] += moire_g
    out[:, :, 2] += moire_b
    return np.clip(out, 0, 255).astype(np.uint8)


def _inject_fluorescent_glare(
    img_rgb: np.ndarray,
    center: Tuple[int, int],
    radius_xy: Tuple[int, int],
    deadzone_radius_xy: Tuple[int, int],
) -> Tuple[np.ndarray, List[int]]:
    """注入荧光灯管斜照玻璃屏幕产生的半透明光晕及中心死白饱和区。"""
    h, w, _ = img_rgb.shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    cx, cy = center
    rx, ry = radius_xy
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    halo = 185.0 * np.exp(-1.8 * (dist ** 2))

    out = img_rgb.astype(np.float32)
    out[:, :, 0] += halo
    out[:, :, 1] += halo
    out[:, :, 2] += halo * 0.96

    drx, dry = deadzone_radius_xy
    dead_mask = (((xx - cx) / drx) ** 2 + ((yy - cy) / dry) ** 2) <= 1.0
    out[dead_mask] = 255.0

    deadzone_bbox = [int(cy - dry), int(cx - drx), int(cy + dry), int(cx + drx)]
    return np.clip(out, 0, 255).astype(np.uint8), deadzone_bbox


def _save_png_and_hash(img_rgb: np.ndarray, path: Path) -> Tuple[str, int, int]:
    Image.fromarray(img_rgb).save(path, format="PNG")
    raw = path.read_bytes()
    h, w, _ = img_rgb.shape
    return hashlib.sha256(raw).hexdigest(), w, h


def _save_jpeg_with_exif6(img_rgb: np.ndarray, path: Path) -> Tuple[str, int, int]:
    """将正置图像逆时针旋转 90 度存储并写入 EXIF Orientation=6（需顺时针 90 度还原）。"""
    rotated_ccw90 = np.rot90(img_rgb, k=1)
    pil_img = Image.fromarray(rotated_ccw90)
    exif = pil_img.getexif()
    exif[0x0112] = 6
    pil_img.save(path, format="JPEG", quality=94, exif=exif.tobytes())
    raw = path.read_bytes()
    h, w, _ = rotated_ccw90.shape
    return hashlib.sha256(raw).hexdigest(), w, h


def _draw_code_editor(
    title: str,
    lines: List[str],
    w: int = 1200,
    h: int = 820,
    font_size: int = 16,
) -> np.ndarray:
    img = Image.new("RGB", (w, h), (30, 34, 42))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, 46], fill=(40, 44, 52))
    draw.text((20, 12), title, font=_font(FONT_MONO_BOLD, 18), fill=(171, 178, 191))

    f_mono = _font(FONT_MONO, font_size)
    y = 70
    line_step = int(font_size * 1.65)
    for idx, text in enumerate(lines, start=1):
        draw.text((22, y), f"{idx:02d}", font=f_mono, fill=(92, 99, 112))
        draw.text((70, y), text, font=f_mono, fill=(220, 223, 228))
        y += line_step
    return np.asarray(img)


def _draw_config_table_page(
    header_title: str,
    rows: List[List[str]],
    draw_inner_vlines: bool = True,
    font_size: int = 16,
    w: int = 1280,
    h: int = 840,
) -> np.ndarray:
    img = _new_canvas(w, h)
    draw = ImageDraw.Draw(img)
    draw.text((60, 40), header_title, font=_font(FONT_CN_BOLD, 24), fill=(17, 24, 39))

    f_cell = _font(FONT_CN, font_size)
    f_hdr = _font(FONT_CN_BOLD, font_size)
    col_x = [60, 320, 580, 880, 1200]
    row_h = max(36, int(font_size * 2.2))
    y = 105

    for r_idx, row in enumerate(rows):
        y2 = y + row_h
        fill_bg = (226, 232, 240) if r_idx == 0 else ((255, 255, 255) if r_idx % 2 == 1 else (248, 250, 252))
        draw.rectangle([col_x[0], y, col_x[-1], y2], fill=fill_bg)
        draw.line([(col_x[0], y), (col_x[-1], y)], fill=(100, 116, 139), width=2)
        draw.line([(col_x[0], y2), (col_x[-1], y2)], fill=(100, 116, 139), width=1)
        if draw_inner_vlines:
            for cx in col_x:
                draw.line([(cx, y), (cx, y2)], fill=(148, 163, 184), width=1)
        else:
            draw.line([(col_x[0], y), (col_x[0], y2)], fill=(100, 116, 139), width=2)
            draw.line([(col_x[-1], y), (col_x[-1], y2)], fill=(100, 116, 139), width=2)

        font_use = f_hdr if r_idx == 0 else f_cell
        for c_idx, val in enumerate(row):
            draw.text((col_x[c_idx] + 12, y + 8), val, font=font_use, fill=(15, 23, 42))
        y = y2

    return np.asarray(img)


def build_samples() -> List[Dict[str, Any]]:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []

    # GS-01: EXIF=6 竖拍横屏 Python 代码图
    code_lines_01 = [
        "from typing import Optional",
        "import asyncio",
        "",
        "async def check_gateway_health(ip: str, port: int = 9092) -> bool:",
        "    try:",
        "        reader, writer = await asyncio.wait_for(",
        "            asyncio.open_connection(ip, port), timeout=5.0",
        "        )",
        "        writer.close()",
        "        return True",
        "    except TimeoutError:",
        "        return False",
    ]
    gs01_clean = _draw_code_editor("gateway_probe.py — VS Code", code_lines_01, w=1180, h=760, font_size=15)
    gs01_path = IMG_DIR / "GS-01_exif_rot90_code.jpg"
    sha, w, h = _save_jpeg_with_exif6(gs01_clean, gs01_path)
    records.append({
        "sample_id": "GS-01",
        "file_name": gs01_path.name,
        "rel_path": f"images/{gs01_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Medium",
        "degradation_tags": ["exif_orientation_6", "dark_ide_code", "8pt_line_numbers"],
        "ground_truth": {
            "expected_exif_orientation": 6,
            "expected_skew_deg": 0.0,
            "expected_language": "python",
            "expected_key_tokens": ["check_gateway_health", "9092", "timeout=5.0", "TimeoutError"],
        },
    })

    # GS-02: +8.5度倾斜网络配置表
    rows_02 = [
        ["交换机端口", "映射 VLAN", "网关 IP", "业务归属"],
        ["eth0/1", "VLAN 100", "10.24.18.1", "生产调度主网"],
        ["eth0/2", "VLAN 200", "10.24.19.1", "监控采集专网"],
        ["eth0/3", "VLAN 300", "10.24.20.1", "带外管理口"],
        ["eth0/4", "VLAN 400", "10.24.21.1", "容灾心跳链路"],
    ]
    gs02_clean = _draw_config_table_page("1.2 核心接入交换机 VLAN 映射表", rows_02, w=1200, h=760)
    center = (600.0, 380.0)
    m_rot = cv2.getRotationMatrix2D(center, -8.5, 1.0)
    gs02_tilted = cv2.warpAffine(gs02_clean, m_rot, (1200, 760), borderValue=(220, 224, 230))
    gs02_path = IMG_DIR / "GS-02_skew_8deg_config.png"
    sha, w, h = _save_png_and_hash(gs02_tilted, gs02_path)
    records.append({
        "sample_id": "GS-02",
        "file_name": gs02_path.name,
        "rel_path": f"images/{gs02_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Medium",
        "degradation_tags": ["affine_skew_+8.5deg", "table_grid", "cn_en_mixed"],
        "ground_truth": {
            "expected_skew_deg": 8.5,
            "table_rows": len(rows_02),
            "table_cols": 4,
            "expected_key_tokens": ["eth0/1", "VLAN 100", "10.24.18.1", "生产调度主网"],
        },
    })

    # GS-03: 梯形透视 + 强高频 RGB 彩虹摩尔纹（SQL 终端）
    sql_lines_03 = [
        "SELECT o.order_id, o.pay_status, i.sku_code, i.unit_price",
        "FROM t_order o",
        "INNER JOIN t_order_item i ON o.order_id = i.order_id",
        "WHERE o.created_at >= '2026-11-01 00:00:00'",
        "  AND o.pay_status IN (1, 2, 4)",
        "ORDER BY o.order_id DESC LIMIT 100;",
    ]
    gs03_base = _draw_code_editor("psql -h 10.24.18.92 -p 5432 -d prod_dispatch", sql_lines_03, w=1240, h=780, font_size=14)
    src_pts = np.float32([[0, 0], [1240, 0], [1240, 780], [0, 780]])
    dst_pts = np.float32([[45, 35], [1190, 68], [1220, 745], [20, 760]])
    h_persp = cv2.getPerspectiveTransform(src_pts, dst_pts)
    gs03_persp = cv2.warpPerspective(gs03_base, h_persp, (1240, 780), borderValue=(18, 20, 24))
    gs03_moire = _inject_rainbow_moire(gs03_persp, strength=34.0)
    gs03_path = IMG_DIR / "GS-03_perspective_moire_terminal.png"
    sha, w, h = _save_png_and_hash(gs03_moire, gs03_path)
    records.append({
        "sample_id": "GS-03",
        "file_name": gs03_path.name,
        "rel_path": f"images/{gs03_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Hardest",
        "degradation_tags": ["perspective_keystone", "high_freq_rgb_moire", "sql_terminal", "8pt_small_font"],
        "ground_truth": {
            "gt_forward_homography_3x3": h_persp.tolist(),
            "gt_inverse_homography_3x3": np.linalg.inv(h_persp).tolist(),
            "expected_language": "sql",
            "expected_key_tokens": ["10.24.18.92", "5432", "t_order_item", "pay_status IN (1, 2, 4)"],
        },
    })

    # GS-04: 荧光灯反光光晕 + 中心死白过曝 + 8pt 小字参数表（最难死区样本）
    rows_04 = [
        ["节点编号", "监听端口", "心跳超时(ms)", "TLS策略"],
        ["node-sh-01", "9092", "15000", "TLSv1.3 双向校验证书"],
        ["node-sh-02", "9093", "15000", "TLSv1.3 双向校验证书"],
        ["node-sh-03", "9094", "18000", "TLSv1.3 强制国密 SM2"],
        ["node-sh-04", "9095", "20000", "TLSv1.3 强制国密 SM2"],
        ["node-sh-05", "9096", "20000", "TLSv1.3 强制国密 SM2"],
    ]
    gs04_base = _draw_config_table_page("2.1 集群节点参数清单 (8pt 密集视图)", rows_04, font_size=12, w=1240, h=780)
    gs04_glare, dead_bbox = _inject_fluorescent_glare(gs04_base, center=(510, 215), radius_xy=(190, 95), deadzone_radius_xy=(75, 36))
    gs04_moire = _inject_rainbow_moire(gs04_glare, strength=18.0)
    gs04_path = IMG_DIR / "GS-04_glare_deadzone_8pt_table.png"
    sha, w, h = _save_png_and_hash(gs04_moire, gs04_path)
    records.append({
        "sample_id": "GS-04",
        "file_name": gs04_path.name,
        "rel_path": f"images/{gs04_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Hardest",
        "degradation_tags": ["specular_glare_deadzone", "illumination_halo", "8pt_dense_table", "moire"],
        "ground_truth": {
            "glare_deadzone_bbox": dead_bbox,
            "expected_review_ticket_type": "GLARE_OCCLUDED",
            "expected_key_tokens": ["node-sh-01", "node-sh-04", "9096", "TLSv1.3 强制国密 SM2"],
        },
    })

    # GS-05: 仅含外框的隐式无内竖线表格
    rows_05 = [
        ["巡检设备", "安装机柜", "当前固件版本", "巡检结论"],
        ["核心防火墙 FW-01", "A区-03柜-U12", "V6.2.104-LTS", "正常通过"],
        ["汇聚交换机 SW-02", "A区-04柜-U08", "V8.1.22-SP1", "正常通过"],
        ["存储阵列 NAS-01", "B区-01柜-U20", "V3.9.4", "告警: 2号盘SMART预警"],
    ]
    gs05_img = _draw_config_table_page("3.1 机房无竖线巡检记录单 (隐式分隔表格)", rows_05, draw_inner_vlines=False, w=1240, h=760)
    gs05_path = IMG_DIR / "GS-05_implicit_borderless_table.png"
    sha, w, h = _save_png_and_hash(gs05_img, gs05_path)
    records.append({
        "sample_id": "GS-05",
        "file_name": gs05_path.name,
        "rel_path": f"images/{gs05_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Hard",
        "degradation_tags": ["implicit_borderless_table", "whitespace_columns", "inspection_sheet"],
        "ground_truth": {
            "table_rows": 4,
            "table_cols": 4,
            "has_inner_vertical_lines": False,
        },
    })

    # GS-06: 多级合并表头 + 跨行跨列复杂规格表
    gs06 = _new_canvas(1240, 780)
    d6 = ImageDraw.Draw(gs06)
    d6.text((60, 40), "4.1 跨行跨列硬件规格与授权矩阵 (colspan / rowspan)", font=_font(FONT_CN_BOLD, 24), fill=(17, 24, 39))
    f_hdr6 = _font(FONT_CN_BOLD, 16)
    f_cel6 = _font(FONT_CN, 15)
    # 表头两行: (0,0,rs=2,cs=1)="环境类型", (0,1,rs=1,cs=2)="算力配置", (0,3,rs=2,cs=1)="离线授权方式"
    d6.rectangle([60, 110, 1180, 390], outline=(71, 85, 105), width=2)
    d6.rectangle([60, 110, 1180, 210], fill=(226, 232, 240), outline=(71, 85, 105), width=2)
    d6.line([(280, 110), (280, 390)], fill=(71, 85, 105), width=2)
    d6.line([(840, 110), (840, 390)], fill=(71, 85, 105), width=2)
    d6.line([(560, 160), (560, 390)], fill=(71, 85, 105), width=1)
    d6.line([(280, 160), (840, 160)], fill=(71, 85, 105), width=1)
    d6.line([(60, 270), (1180, 270)], fill=(71, 85, 105), width=1)
    d6.line([(280, 330), (1180, 330)], fill=(71, 85, 105), width=1)
    d6.text((120, 148), "环境类型", font=f_hdr6, fill=(15, 23, 42))
    d6.text((515, 124), "算力配置", font=f_hdr6, fill=(15, 23, 42))
    d6.text((380, 174), "CPU 架构", font=f_hdr6, fill=(15, 23, 42))
    d6.text((660, 174), "加速卡", font=f_hdr6, fill=(15, 23, 42))
    d6.text((945, 148), "离线授权方式", font=f_hdr6, fill=(15, 23, 42))
    d6.text((100, 230), "通用商业云", font=f_cel6, fill=(15, 23, 42))
    d6.text((340, 230), "x86-64 EPYC", font=f_cel6, fill=(15, 23, 42))
    d6.text((610, 230), "NVIDIA L40S", font=f_cel6, fill=(15, 23, 42))
    d6.text((880, 230), "VPC 租户签名", font=f_cel6, fill=(15, 23, 42))
    d6.text((100, 315), "政企信创机房", font=f_cel6, fill=(15, 23, 42))
    d6.text((340, 290), "鲲鹏 920 ARM64", font=f_cel6, fill=(15, 23, 42))
    d6.text((610, 290), "昇腾 910B NPU", font=f_cel6, fill=(15, 23, 42))
    d6.text((880, 290), "Ed25519 + 加密狗", font=f_cel6, fill=(15, 23, 42))
    d6.text((340, 350), "龙芯 3C5000", font=f_cel6, fill=(15, 23, 42))
    d6.text((610, 350), "纯 CPU ONNX", font=f_cel6, fill=(15, 23, 42))
    d6.text((880, 350), "物理离线一体机", font=f_cel6, fill=(15, 23, 42))
    gs06_path = IMG_DIR / "GS-06_nested_merged_table.png"
    sha, w, h = _save_png_and_hash(np.asarray(gs06), gs06_path)
    records.append({
        "sample_id": "GS-06",
        "file_name": gs06_path.name,
        "rel_path": f"images/{gs06_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Hard",
        "degradation_tags": ["multi_level_header", "colspan_2", "rowspan_2"],
        "ground_truth": {
            "table_rows": 5,
            "table_cols": 4,
            "merged_cells": [
                {"row": 0, "col": 0, "rowspan": 2, "colspan": 1, "text": "环境类型"},
                {"row": 0, "col": 1, "rowspan": 1, "colspan": 2, "text": "算力配置"},
                {"row": 0, "col": 3, "rowspan": 2, "colspan": 1, "text": "离线授权方式"},
                {"row": 3, "col": 0, "rowspan": 2, "colspan": 1, "text": "政企信创机房"},
            ],
        },
    })

    # GS-07 / GS-08 / GS-09: 连续滚动长日志/配置图（刻意在视口边界腰斩字符行）
    long_lines = [f"PARAM_{idx:03d} = 10.24.{idx // 10}.{10 + idx}  # 调度节点配置项 {idx:03d}" for idx in range(1, 37)]
    canvas_long = _draw_code_editor("cluster_nodes_scroll.conf", long_lines, w=1160, h=1450, font_size=16)
    crop_specs = [
        ("GS-07", "GS-07_scroll_frame_01.png", 0, 520, "bottom_edge_clipped"),
        ("GS-08", "GS-08_scroll_frame_02.png", 350, 870, "both_edges_clipped"),
        ("GS-09", "GS-09_scroll_frame_03.png", 710, 1230, "top_edge_clipped"),
    ]
    for sid, fname, y0, y1, clip_tag in crop_specs:
        patch = canvas_long[y0:y1, :, :]
        fpath = IMG_DIR / fname
        sha, w, h = _save_png_and_hash(patch, fpath)
        records.append({
            "sample_id": sid,
            "file_name": fname,
            "rel_path": f"images/{fname}",
            "source_sha256": sha,
            "dimensions": {"width": w, "height": h},
            "difficulty": "P0-Hard",
            "degradation_tags": ["scroll_stitching_sequence", clip_tag],
            "ground_truth": {
                "scroll_group_id": "SCROLL_GRP_01",
                "virtual_canvas_y_offset_px": y0,
                "viewport_height_px": y1 - y0,
            },
        })

    # GS-10 / GS-11: 跨时序配置覆盖冲突对（v1 误配置报错 vs v2 最终收敛）
    v1_lines = [
        "[2026-11-19 14:02:11] Configuring Kafka Broker...",
        "broker.id=101",
        "listeners=PLAINTEXT://0.0.0.0:9092",
        "request.timeout.ms=3000",
        "ERROR: TimeoutException waiting for metadata after 3000ms!",
    ]
    v2_lines = [
        "[2026-11-19 14:05:40] Updating Kafka Broker Timeout...",
        "broker.id=101",
        "listeners=PLAINTEXT://0.0.0.0:9092",
        "request.timeout.ms=15000",
        "INFO: Cluster metadata synced successfully (15000ms).",
    ]
    for sid, fname, lines, ts, val, state in [
        ("GS-10", "GS-10_temporal_conflict_v1.png", v1_lines, "2026-11-19T14:02:11Z", "3000", "OBSOLETE_ERROR"),
        ("GS-11", "GS-11_temporal_conflict_v2.png", v2_lines, "2026-11-19T14:05:40Z", "15000", "CONVERGED_FINAL"),
    ]:
        img_t = _draw_code_editor(f"server.properties ({state})", lines, w=1180, h=620, font_size=16)
        fpath = IMG_DIR / fname
        sha, w, h = _save_png_and_hash(img_t, fpath)
        records.append({
            "sample_id": sid,
            "file_name": fname,
            "rel_path": f"images/{fname}",
            "source_sha256": sha,
            "dimensions": {"width": w, "height": h},
            "difficulty": "P0-Hard",
            "degradation_tags": ["temporal_state_override", state.lower()],
            "ground_truth": {
                "timestamp": ts,
                "config_key": "request.timeout.ms",
                "config_value": val,
                "expected_temporal_role": state,
            },
        })

    # GS-12: 双栏中英混排 + 页眉页脚噪点 + 英文断词连字符
    gs12 = _new_canvas(1280, 860)
    d12 = ImageDraw.Draw(gs12)
    f_meta = _font(FONT_CN, 13)
    f_h1 = _font(FONT_CN_BOLD, 24)
    f_body = _font(FONT_CN, 16)
    d12.text((60, 18), "绝密工程内部规范 — 第 12 页", font=f_meta, fill=(148, 163, 184))
    d12.text((60, 75), "5. 双栏架构与并发控制规约", font=f_h1, fill=(15, 23, 42))
    left_col = [
        "系统在多线程并发处理高分辨率底片时，",
        "采用显式锁定内存池机制防止数据换出。",
        "All preprocessing tasks run concur-",
        "rently across worker threads without",
        "blocking the review queue interface.",
    ]
    right_col = [
        "在右栏拓扑校验阶段，所有跨行合并表格",
        "必须通过二维物理占用矩阵验证，确保",
        "生成的 OpenXML Transitional 标签严格",
        "满足列宽守恒定理并兼容旧版办公软件。",
    ]
    for i, line in enumerate(left_col):
        d12.text((60, 145 + i * 34), line, font=f_body, fill=(30, 41, 59))
    for i, line in enumerate(right_col):
        d12.text((680, 145 + i * 34), line, font=f_body, fill=(30, 41, 59))
    d12.rectangle([680, 320, 1180, 560], fill=(241, 245, 249), outline=(71, 85, 105), width=2)
    d12.text((830, 425), "[架构拓扑图切片占位区域]", font=f_body, fill=(51, 65, 85))
    d12.text((580, 825), "- 12 -", font=f_meta, fill=(148, 163, 184))
    gs12_path = IMG_DIR / "GS-12_dual_column_mixed_zh_en.png"
    sha, w, h = _save_png_and_hash(np.asarray(gs12), gs12_path)
    records.append({
        "sample_id": "GS-12",
        "file_name": gs12_path.name,
        "rel_path": f"images/{gs12_path.name}",
        "source_sha256": sha,
        "dimensions": {"width": w, "height": h},
        "difficulty": "P0-Medium",
        "degradation_tags": ["dual_column_xy_cut", "dehyphenation_concurrently", "header_footer_noise", "embedded_diagram"],
        "ground_truth": {
            "is_multi_column": True,
            "expected_dehyphenated_word": "concurrently",
            "header_footer_filtered": ["绝密工程内部规范 — 第 12 页", "- 12 -"],
        },
    })

    # 写入单文件标注与总 manifest.json
    for rec in records:
        ann_path = ANN_DIR / f"{rec['sample_id']}.json"
        ann_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "dataset_name": "DocReconstruct-GoldSamples-v1.0",
        "total_samples": len(records),
        "hardest_samples": ["GS-03", "GS-04"],
        "samples": [
            {
                "sample_id": r["sample_id"],
                "file_name": r["file_name"],
                "rel_path": r["rel_path"],
                "annotation_path": f"annotations/{r['sample_id']}.json",
                "source_sha256": r["source_sha256"],
                "difficulty": r["difficulty"],
                "degradation_tags": r["degradation_tags"],
            }
            for r in records
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    generated = build_samples()
    print(f"Generated {len(generated)} Gold Samples in {OUT_DIR}")
