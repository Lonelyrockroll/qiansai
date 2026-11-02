# 仅谱峰版观察页

本配置保留 FPGA 本地 64 频点实时频谱、32/31 独立测试音与 LAST I2S 起音计时。波形和单声道延时 XY 交给电脑观察；需要三种图都脱离电脑展示时，请使用主工程的完整配置。

`fpga/audio_monitor.v` 是唯一有别于完整版的 FPGA 输入。测试入口为 `python profiles/spectrum-only/tests/monitor/run.py --native --render`，状态文字与峰位标记可用 `--status-only --render` 单独检查。

当前完整工程已修复按住 H15 重复触发；使用同一修复扫描器的仅谱峰版正在重布局。旧 User Code `0x00005A96` 属于修复前候选。本次新的码流、完整时序和物理资源结果待验证通过后更新。
