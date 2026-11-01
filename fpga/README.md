# Tang Mega 60K NEO 实时合成器

v27 在原 32 分量钢琴工程上加入滑音和颤音，钢琴直通。控制键盘接 J18，USB-A 选择开关置于 FPGA。[旋钮手势、试听和验证](../EXPRESSION.md)

打开同目录的 `synth_display.gprj`，顶层为 `synth_display_top`。本目录包含 32 分量演奏钢琴版的全部综合输入，包括 RTL、引脚与时序约束、屏幕字库、鼓组和 USB 的 ROM。

在本目录用 Python 3 运行 `python check_sources.py` 检查工程依赖，然后用 Gowin 教育版执行 `gw_sh.exe build.tcl`。v27 SRAM User Code 为 `0x0000DC5C`。[当前码流](../firmware/knob-expression.zip)；原 32 分量钢琴基线为 `0x0000D27F`。
