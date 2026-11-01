# Tang Mega 60K NEO · 32 键实时合成器

当前 v30 新增 MIDI 屏幕演奏指引，手机选单轨传入后，板卡独立计时，在屏幕上方完整显示 32 个白键的当前目标、预告和实按反馈。[指引说明与 PDF 可行性](SCREEN-GUIDE.md)。音频保留 v29 的四子帧 DAC 输出、32 分量演奏钢琴，以及其余旋律音色的滑音与颤音。[模拟输出测量](OUTPUT-HARMONICS.md) · [旋钮说明](EXPRESSION.md)。工程包含 32 键扫描、旋律与 12 键打击垫、Loop、HDMI、USB 控制键盘、蓝牙录音和音频电平表。

* **打开 FPGA 工程**　使用 Gowin EDU V1.9.11.03 打开 `fpga/synth_display.gprj`，器件已设为 GW5AT-LV60PG484AC1/I0。命令行构建时从 `fpga` 目录运行 `gw_sh.exe build.tcl`，并确保 PATH 上有 Python 3。全部源码、约束和 ROM 均随包提供。
* **运行已验证的版本**　当前 v30 使用 [screen-guide.zip](firmware/screen-guide.zip) 中的 `screen-guide.fs`，SRAM User Code 为 `0x0000BB8F`。上一版 v29 保存在 [quad-output.zip](firmware/quad-output.zip)。用 Gowin Programmer 选择 GW5AT-60B、SRAM Program，经 DEBUG-USB2 临时下载。
* **Windows 上位机**　在 `realtime_synth/host` 运行 `python server.py --port 8767`，在浏览器打开 `http://127.0.0.1:8767/`。
* **安卓录音与 MIDI 指引**　`realtime_synth/android_recorder` 提供 Android Gradle 工程、协议测试、应用说明和 `dist/TangRecorder-1.1.apk`。传曲完成后可断开手机，板卡继续指引；上传曲目断电不保留。
* **调音和验证**　`realtime_synth/throughput_eval/experiments/modal32/musical` 包含新钢琴系数生成器、音频对照、板测 PCM、C4 逐峰表及压力测试。两次 C4 起音均测到 32 个目标峰。完整层级用于复现开发脚本，当前量产前验证工程的直接入口为上面的 `fpga/synth_display.gprj`。
* **硬件与外壳**　从仓库根目录另取键盘 PCB、V1.3 可编辑模型、装配和 3D 打印包。

初始归档包（不含此后的 v27～v30 更新）：[软件工程](TangSynth-System.zip)、[当时固件](TangSynth-Firmware.zip)。当前工程请使用仓库中的 `fpga/`、`realtime_synth/` 及各版本说明。硬件包：[键盘 PCB](Keyboard-PCB.zip)、[外壳源模型](Keyboard-Enclosure-CAD.zip)、[装配](Keyboard-Enclosure-Assembly.zip)、[打印件](Keyboard-Enclosure-Print.zip)。初始归档的文件摘要见 [SHA256SUMS.txt](SHA256SUMS.txt)。
