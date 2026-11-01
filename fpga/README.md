# Tang Mega 60K NEO 实时合成器

打开同目录的 `synth_display.gprj`，顶层为 `synth_display_top`。本目录包含 32 分量演奏钢琴版的全部综合输入，包括 RTL、引脚与时序约束、屏幕字库、鼓组和 USB 的 ROM。

在本目录用 Python 3 运行 `python check_sources.py` 检查工程依赖，然后用 Gowin 教育版执行 `gw_sh.exe build.tcl`。实板参考码流 User Code 为 `0x0000D27F`，完整软件包内附同版码流和 C4 测量记录。
