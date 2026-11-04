# 扩展迭代 PRD - Iteration 7：软件安全防逆向与离线授权保护

## 1. 迭代概述与交付目标

### 1.1 业务诉求
针对 **Tier 1 政企客户（涉密、物理隔离机房）** 及商业化软件知识产权保护，软件交付面临极其严峻的安全威胁：
1. **反编译与源码泄露**：Python 源码或标准 `pyc` 字节码极易被逆向工具（如 Decompyle++, PyInstaller Extractor）反编译，泄露核心算法流水线与私有 Prompt 资产；
2. **离线单机破解盗版**：物理隔离内网无法连接云端授权服务器，攻击者极易通过内存 Patch 或文件替换绕过许可证校验；
3. **机密数据泄露审计风险**：在涉密机房使用后，若运算产生的临时图像缓存、模型中间张量留在磁盘，一旦通过数据恢复软件还原，将构成严重泄密违规。
Iteration 7 的核心使命是构建**“企业级纵深防御体系（Defense-in-Depth）”**，实现**“机器码二进制固化、非对称硬件指纹授权、反动态调试、防时间回拨与机密数据军工级粉碎”**。

### 1.2 阶段验收核心指标
1. **源码反编译阻断率**：使用主流自动化 Python 反编译器反编译核心算法，反编译成功率为 $0\%$；
2. **离线授权伪造阻断率**：基于 Ed25519 椭圆曲线非对称数字签名，未经私钥签发的伪造 License 识别阻断率 $100\%$；
3. **涉密临时文件恢复阻断率**：经系统安全擦除的临时中间数据，使用行业级数据取证软件（如 EnCase、DiskGenius 深度扫描）恢复成功率为 $0\%$；
4. **单机时间篡改阻断率**：通过修改操作系统 BIOS/系统时间尝试延长授权有效期的阻断率 $100\%$。

---

## 2. 详细功能需求规格 (Functional Requirements)

### FR-701: 核心代码机器码编译固化与符号剥离 (Machine-Code Compilation & Symbol Stripping)
- **处理逻辑**：
  - 严禁使用普通 PyInstaller 打包明文 `.py` 或纯 `.pyc` 字节码交付；
  - 核心编排引擎、AST 纠偏、坐标映射等高价值模块，强制采用 **Nuitka / Cython** 编译为原生 C/C++ 动态链接库（Windows `.pyd` / Linux `.so`）；
  - **符号剥离（Strip Symbols）**：剔除所有函数名、局部变量名调试符号，关键字符串常量采用动态 XOR 混淆加载；
  - 外部只暴露初始化接口，内部逻辑直接在操作系统原生机器指令层执行。

### FR-702: 跨平台多维硬件指纹提取与 Ed25519 离线验签 (Hardware Fingerprint & Licensing)
- **处理逻辑**：
  - **硬件指纹熵池采集**：
    - 主板 UUID（`wmic baseboard get serialnumber` / `/sys/class/dmi/id/product_uuid`）；
    - CPU 物理 ID（CPUID 指令提取）；
    - 主网卡物理 MAC 地址；
    - 系统引导磁盘底层硬件序列号；
  - **硬件绑定哈希生成**：将上述硬件特征加盐执行 SHA-256 计算，生成机器唯一指纹 `Device_Fingerprint`；
  - **离线验签算法**：采用高强度 **Ed25519 现代椭圆曲线数字签名**算法：
    - 研发端持有官方离线私钥（Private Key），根据用户提供的指纹签发加密 License 文件；
    - 客户端仅内置官方公钥（Public Key），纯本地执行验签，无需任何网络外联心跳；
  - **高保密实体加密狗支持**：在涉密军工政企场景，支持集成 USB 硬件加密狗（如深思数盾/威步加密锁），实现物理硬件插拔管控。

### FR-703: 运行时防动态调试与内存置零擦除 (Anti-Debugging & Memory Zeroing)
- **处理逻辑**：
  - **反调试探针 (Anti-Debug Probe)**：
    - Windows 端监控 `IsDebuggerPresent()`, `CheckRemoteDebuggerPresent()`, 硬件断点寄存器（DR0~DR3）；
    - 检测到常见逆向分析进程（x64dbg, IDA Pro, CheatEngine, Frida）附加时，主进程立即触发内存自毁并退出，退出码伪装为常规系统内存不足错误；
  - **敏感内存即时置零 (Zero-Fill Memory)**：
    - 针对模型解密密钥、未脱敏的临时图像像素矩阵，在使用完成后立即调用 `SecureZeroMemory()` 物理清空内存缓冲区，防止内存 Dump 取证泄露。

### FR-704: 防时间回拨与单调递增时钟守护 (Anti-Time-Rollback Daemon)
- **处理逻辑**：
  - 在完全断网机房中，用户无法同步 NTP 公网授时，可能通过修改操作系统时钟达到无限期试用的目的；
  - **持久化单调递增时钟**：在加密隐藏存储区（如 Windows 注册表加密键值或隐藏文件块）记录系统最近一次正常运行的绝对时间戳与运行时长累积计数器；
  - **异常判定**：若当前系统时间早于历史记录的最大时间戳，或运行时长计数出现倒退，判定为时间回拨作弊行为，立即锁定许可证并提示“系统时钟异常，已自动安全锁定”。

### FR-705: 涉密临时数据生命周期军工级销毁 (DoD 5220.22-M Secure Sanitization)
- **处理逻辑**：
  - 任务处理过程中的中间切片、临时 OCR 缓存文件，一律存放在加密虚拟内存盘（RAM Disk）或专设的加密临时缓存目录中；
  - **物理擦除协议**：文档交付导出完毕或任务取消时，系统不使用普通操作系统 `delete`（普通删除只抹除索引），而是强制执行 **DoD 5220.22-M 三遍覆写标准**：
    - 第一遍：全部扇区写入固定常数 `0x00`；
    - 第二遍：全部扇区写入固定常数 `0xFF`；
    - 第三遍：全部扇区写入加密伪随机伪数据，最后执行截断删除；
  - 彻底杜绝底层数据被恢复的可能。

---

## 3. 核心数据契约：离线许可证契约 (LicenseManifest Schema)

```json
{
  "license_version": "2.0",
  "issuer": "DocReconstruct Security Authority",
  "issued_to": "某省税务局信息中心",
  "issue_date": "2026-11-05",
  "expiry_date": "2027-11-05",
  "hardware_binding": {
    "device_fingerprint_sha256": "4a7d1ed414474e4033ac29ccb8653d9b036573c9c9918073eb4ea30a57e3f8ec",
    "allow_cpu_change": false,
    "allow_mac_change": true
  },
  "tier": "Tier_1_Government_Offline",
  "features": {
    "max_concurrent_channels": 4,
    "enable_video_processing": true,
    "enable_click_to_source": true,
    "max_monthly_page_quota": -1
  },
  "digital_signature_ed25519": "3b2e59df6f157f...[128 hex chars]...8b9c1d"
}
```

---

## 4. 边界场景与异常防御矩阵

| 边界场景 | 现象描述 | 确定性防御方案 |
| :--- | :--- | :--- |
| **合法硬件微小变动** | 客户服务器更换了一块备用网卡，导致 MAC 地址改变 | 采用硬件指纹容错策略：要求 4 项核心硬件中至少 3 项绝对匹配，防止正常硬件维护导致系统锁死 |
| **虚拟机/Docker 伪造 UUID** | 攻击者在虚拟化环境中克隆虚拟机，硬件 UUID 完全一致 | 增加对硬件底层 I/O 延迟抖动测量与 Hypervisor 特征探测，区分宿主机物理机与克隆容器环境 |
| **非正常断电导致临时文件残留** | 处理到一半机房断电，未触发正常 DoD 销毁流程 | 在主程序下一次启动初始化（Init）阶段，自动扫描临时目录，对上一轮未完成的残留文件强制执行擦除 |
