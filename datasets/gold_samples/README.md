# DocReconstruct Gold Samples 基准测试数据集 (`v1.0`)

## 1. 数据集定位

本目录存储用于验证多源有损视觉文档逆向重构流水线的 **12 组标准退化屏摄 Gold Samples** 及其确定性 Ground Truth 标注（含物理退化标签、EXIF 旋转真值、逆单应性矩阵真值、高光死白遮挡边界框、复杂合并表格结构与连续滚动接缝偏移）。

## 2. 样本全览矩阵

| 样本编号 | 文件路径 | 难度评级 | 核心退化特征与验收重点 |
| :--- | :--- | :--- | :--- |
| **GS-01** | `images/GS-01_exif_rot90_code.jpg` | `P0-Medium` | 真实 JPEG EXIF `Orientation=6`（顺时针 $90^\circ$ 归一化）+ 深色 IDE Python 代码块 |
| **GS-02** | `images/GS-02_skew_8deg_config.png` | `P0-Medium` | $+8.5^\circ$ 手持仿射倾斜 + 网络 VLAN 配置表（校验霍夫校平与 $T^{-1}$ 逆反投） |
| **GS-03** | `images/GS-03_perspective_moire_terminal.png` | **`P0-Hardest`** | **强斜拍梯形透视畸变 + 高频 RGB 彩虹摩尔纹 + 14px 小字 SQL 终端** |
| **GS-04** | `images/GS-04_glare_deadzone_8pt_table.png` | **`P0-Hardest`** | **荧光灯半透明光晕 + 中心死白饱和过曝（`>=253`）+ 8pt 密集参数表 + 摩尔纹** |
| **GS-05** | `images/GS-05_implicit_borderless_table.png` | `P0-Hard` | 仅含外框、内部全靠空白分隔的隐式无竖线巡检记录表 |
| **GS-06** | `images/GS-06_nested_merged_table.png` | `P0-Hard` | 多级表头 + `colspan=2` / `rowspan=2` 跨行跨列合并表（OpenXML 网格不变量测试） |
| **GS-07 ~ GS-09** | `images/GS-07_scroll_frame_01..03.png` | `P0-Hard` | 3 帧连续滚动配置序列，刻意在视口顶/底边缘腰斩文本行（验证接缝超平面 $Y_{\text{seam}}$） |
| **GS-10 ~ GS-11** | `images/GS-10..11_temporal_conflict_v1..v2.png` | `P0-Hard` | 跨时序参数修改冲突对（`v1: timeout=3000ms` 报错 $\to$ `v2: timeout=15000ms` 收敛） |
| **GS-12** | `images/GS-12_dual_column_mixed_zh_en.png` | `P0-Medium` | 双栏中英混排（`concur-rently` 断词缝合）、页眉页脚过滤与嵌入式插图切片 |

## 3. 最难样本专项说明（`GS-03` 与 `GS-04`）

- **`GS-04_glare_deadzone_8pt_table.png`**：模拟荧光灯管直打玻璃屏幕的真实物理退化——外部光晕区（灰度 `210~250`）仍保留微弱局部梯度，需靠大核形态学背景除法恢复 8pt 暗字；而中心死白过曝区（`R=G=B>=253`）像素信息已发生物理截断，必须精准检出 `glare_deadzone_bboxes` 并触发 `GLARE_OCCLUDED` 工单，严禁概率脑补。
- **`GS-03_perspective_moire_terminal.png`**：模拟强斜拍叠加高频 RGB 子像素干涉彩纹，传统空域双边滤波极易糊掉终端内的数字与标点（如 `10.24.18.92`、`5432`），需通过 YCbCr 色度剥离 + 保护正十字轴的 2D FFT 定向陷波去除周期摩尔纹。

## 4. 数据集完整性与自动化测试

```bash
python -m unittest discover -s tests -v
```
