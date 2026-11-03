# 仅谱峰版观察页

当前 MIDI v33 码流为 `0x0000FAE1`，使用布局选项 2，支持 BMV51M001 接入 AA19。下载与接线见 [MIDI 说明](../../MIDI-INPUT.md)。

分级菜单初版的 User Code 为 `0x000090FB`。从首页进入「设置 → 声谱观察」。该版完整构建配方和码流见[工程包](../../output/Tang-分级菜单UI-v32.zip)。

本配置在 FPGA 屏上保留完整的 64 个频点、实际峰数与 LAST I2S 计时。测试音占第 1、3、5…63 个频点，短按 B 切换 32/31 音，测试时转动 B 可移动缺口。需要板上同时显示波形与单声道延时相图时，使用完整版。

早期键盘扫描修复版的 User Code 为 `0x00005463`。其码流 SHA256 为 `2675c1d068245213378d3173010f7ba08c77db51c6a846cf4c43ee3d28b68969`。旧 `0x00005A96` 属于此次扫描修复前的历史版本。

最终布局占用 47,038 / 59,904 Logic、24,986 / 60,780 FF、117 / 118 BSRAM 和 57 / 118 DSP。与同一顶层、同一扫描器的完整版相比，净省 2,221 Logic、1,028 FF 和 1 块物理 BSRAM。

系统时钟目标 50 MHz，报告 Fmax 50.068 MHz。像素/USB 的 Fmax 分别为 49.745 / 74.008 MHz。四个约束时钟域 setup/hold 检查均通过，保留 PR1014 提示且系统时序裕量较小。

## 构建和核对

在可调用 Gowin EDU V1.9.11.03 `gw_sh.exe` 的 PowerShell 中，从仓库根目录执行以下命令。目标目录须新建或为空。`prepare_monitor_project.py` 会为当前版本生成带布局选项 2 的独立工程。

```powershell
python tools/prepare_monitor_project.py spectrum-only build/v32-spectrum-only
Push-Location build/v32-spectrum-only
gw_sh.exe build.tcl *> build.log
Pop-Location
python tools/validate_guide_build.py build/v32-spectrum-only --profile spectrum-only
```

运行 `python profiles/spectrum-only/tests/monitor/run.py --native --render` 可复现 0、1、2、32、31、0 峰及黄金图。状态文字和缺峰标记可用 `--status-only --render` 单独检查。

详细波形/延时 XY 的电脑入口及综合/物理资源的不同统计口径，见仓库根目录《资源与电脑分析.md》。本文列出的验证为实际 RTL 和整机布局；实板记录以具体下载码流为准。
