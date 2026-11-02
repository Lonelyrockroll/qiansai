# v32 实板验收记录

当前目录的 `after_jtag.log` 标识实际临时下载的码流。`spectrum.json` 记录板上频点、声部、抱持音接管及采样帧计数。`all32.pcm`、`off16.pcm`、`off17.pcm` 各含 4,096 个最终 16 位小端样本，独立 FFT 见 `fft.csv`。三次采集使用相同的合成与输出路径。测试时静音模拟监听。

`onset_board.json` 对应一次独立的 H15（默认 C4）实物测量。起点为 FPGA 接受来自琴板的 Note On，终点为第一个完整非零的标准 I²S 左声道字；看按住的稳定性要比较该次按下和松开的计数差值。`heard.json` 标明人工观察属于哪个码流。

| 中间版档案 | 实板观察 |
|---|---|
| `intermediate-F939/` | 实际按键松开，但路由仍保有 3 个现场声部，阻碍观察页切换。失效的 107 µs 读数无法归给这次按键。 |
| `intermediate-C69B/` | 现场人员已确认 LAST I2S 保持、32 峰、31 峰和缺口移动；实测 C4 数字段 93 µs。单次长按意外出现 962 个 ON、1 个 OFF。`local_controls.json` 是这次观察的逐笔记录。 |

早期码流的原始记录保留在各自目录内。保持输入复现旧问题及修正版的 RTL／门级对照见[扫描器门级记录](../contest_latency/results/gate_hold/validation.json)。
