# qiansai

[新版分级菜单操作](SCREEN-NAVIGATION.md) · [完整 Gowin 工程、码流与实板记录](output/Tang-分级菜单UI-v32.zip)

新版 `0x000090FB` 在顶部完整显示 32 个白键，首页提供音色、效果、循环录制、曲目指引和设置五个入口。旋转 B 选择，短按 B 执行，按住 B 旋转调音量，短按 A 静音回首页。

![分级菜单首页](tests/guide_ui/results/hierarchical/home.png)

[琴键音量 40% 版本](VOLUME-RANGE.md)将实体琴键上限放宽到 40%，当前推荐试听设置为 32%，基于 v32 FX2，码流为 `0x00000239`。[下载码流与验证包](output/Tang-琴键音量40-v32FX2.zip)

此前的琴键音量 40% 版使用仅谱峰显示配置。解压该版下载包后，可用 Gowin 打开其中的 `FPGA工程/synth_display.gprj`，对应源码、引脚和时序校验结果一并保存在包内。

[v32 FX2 效果增强](EFFECTS-ENHANCED.md)统一板载菜单与上位机预设，提供长尾混响、约 320 ms 回声和更深的合唱调制。[码流与统一试听包](output/Tang-效果增强-v32FX2.zip)

[演奏延迟实测展示包](output/Tang-延迟实测展示.zip) · [示波器接线和测量步骤](延迟测试接线.md)。在 Windows 工程目录双击「启动延迟实测」可读取板上 LAST I2S、导入示波器波形或试听 Ampero 的耳机输出录音。
[下载 v32 初始脱机验收包](output/Tang-脱机验收-v32.zip)。该包保留 `0x0000365B` 完整观察页的实测版本 `Tang-v32-full.fs`，以及同阶段的 `Tang-v32-spectrum-only.fs`。J18 的旋钮 B 选菜单 13「声谱观察」，短按进入 LIVE，再短按展示 32 峰和 31 峰。

延迟测试的原始采集档案保存在「延迟实测展示包」中，解压到本地工程目录后即可读取文档中 `output/latency/` 路径对应的 CSV 和 JSON。

v32 增加脱机 32 峰测试、FPGA 音频观察页、数字起音计时、轻重触键归一化、安卓在线曲谱和白键互换。[台上操作与指标对照](现场验收.md) · [第 115 条及测量方案](赛题二问答与验收测量.md) · [安卓 1.3](realtime_synth/android_recorder/dist/TangRecorder-1.3.apk) · [资源与电脑分析](资源与电脑分析.md) · [独立电脑工具](output/Tang-PC-Audio-Tools.zip)

v31 加入手机选 PDF、蓝牙传页、板卡全屏显示与翻页。[曲谱验收步骤](FULLSCREEN-SCORE.md) · [安卓 1.2](realtime_synth/android_recorder/dist/TangRecorder-1.2.apk) · [示范谱](output/pdf/score-demo.pdf)

v30 增加手机 MIDI 传曲与板卡独立计时的屏幕演奏指引，32 个白键在上方完整一行显示。[操作与容量说明](SCREEN-GUIDE.md) · [安卓 1.1](realtime_synth/android_recorder/dist/TangRecorder-1.1.apk)

![屏幕演奏指引](tests/guide_ui/results/guide.png)

音频保留 v29 的四子帧输出。[连续 8 秒试听与工程入口](OUTPUT-HARMONICS.md)

v28 已校准板载 DAC 的耳机输出。[连续试听与校准记录](OUTPUT-CALIBRATION.md)

v27 支持 J18 旋钮滑音、颤音和按转音量。Gowin 工程入口在 `fpga/`。[手势与验证](EXPRESSION.md)

- [完整工程与使用说明](PROJECT.md)
- [Gowin FPGA 工程](fpga/synth_display.gprj)
- [上一版 32 分量钢琴完整包](TangSynth-System.zip)
