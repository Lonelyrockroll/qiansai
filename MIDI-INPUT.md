# Keystation 61 MK3 五针 MIDI 输入

v33 在分级菜单版工程上增加 BMV51M001 输入。MIDI 数据由 FPGA 内的串口接收器、消息解析器、事件队列和声部分配逻辑处理，进入现有实时音源、效果器和 Loop。演奏输入在电脑、自制琴板和 MIDI 键盘之间切换，J18 的十二个打击垫可同时演奏。

本次交付码流为 `0x0000FAE1`，已于 2026 年 11 月 3 日临时下载到 Tang 并完成 JTAG 回读。板上当前选择 MIDI 输入、钢琴、25% 音量，保持静音。Keystation 实际接线与试弹待用户完成。

## 接线与上电

使用 Tang Mega 60K、NEO Dock 31004 和明确包含 `midi_rx / AA19` 输入约束的 v33 码流。先在断电时接好模块供电、地和五针线，RX 暂留空。上电后临时下载并核对 v33，保持该程序运行，再接最后一根 RX 数据线。

| BMV51M001 | Tang NEO 31004 |
| --- | --- |
| VDD | J8-1，3.3 V |
| GND | J8-3，GND |
| RX | J8-5，AA19 / PMOD1_IO6，FPGA 输入 |
| TX、NC | 留空 |

J8 位于 KEY.0 与 POWER 之间，靠 HDMI 一侧。按板上 1 脚标记核对针号，插口正面与焊盘侧的方向互为镜像。J8-7/8 与蓝牙网络相连，J8-9～12 已承担音频和观测信号。

五针线从 Keystation 的 MIDI OUT 接 BMV51M001 的 MIDI IN。Keystation 用自身 USB 供电。模块的 RX 是光耦后的逻辑输出，6N138 的输出上拉至模块 VDD，因此本接法使用 3.3 V。模块参数与线路以原厂资料为据。[BMV51M001 产品页](https://www.bestmodulescorp.com/tc/bmv51m001.html) · [原厂线路图](https://www.bestmodulescorp.com/en/amfile/file/download/file/2107/product/1316/)

Keystation 开机后，按 **Advanced**，再按琴键上方标有 **MIDI OUT** 的黑键。编辑模式退出后，琴键数据从五针口发送。该步骤见原厂手册的 MIDI Out 小节。[Keystation 61 MKIII 手册第 14 页](https://cdn.inmusicbrands.com/m-audio/maudio_documentation/Keystation%2061%20MKIII%20-%20User%20Guide%20-%20v1.6.pdf#page=14)

SRAM 临时下载在断电后失效。下一次重新上电前先断开 RX，开机重载这份 v33 程序后，再恢复 RX 数据连接。历史 `control_pmod` 固件曾将 AA19 配成输出，其接线用途与本版不同。

## 使用

1. 在屏幕进入「设置」，选第一项输入来源，短按 B 在 PC、扫描、MIDI 之间轮换。切换会静音。已有 Loop 正在播放、录制或等待录制时，先结束该操作。
2. 选择「输入 MIDI」后，短按 A 回首页，短按 B 开始演奏并等待功放预热。
3. 按键发声，松键进入该音色的释放阶段。默认延音关闭，使用现有键盘即可测试。
4. 按住 B 并旋转调琴键音量。短按 A 或上位机「全部静音」停止演奏。音色、效果、鼓组和 Loop 的入口沿用分级菜单。

MIDI 模式下，音符在没有后续 MIDI 消息时继续保持。上位机断开或关闭页面后，FPGA 可独立演奏。切回 PC 输入时，电脑控制的心跳保护恢复生效。

屏幕设置页显示接收字节、支持的消息事件、异常累计和延音状态，三个数字显示各自计数器的低 16 位。上位机 MIDI 面板显示完整字节／事件计数、帧错误、队列溢出、按住音数、最近音符、力度、通道和满复音替换次数，并提供清计数按钮。

MIDI 按真实音高发声，包含黑键和 0～127 的音符编号。屏幕上方的 32 白键继续显示 C2～F6 范围内的白键反馈，最近音符编号可在上位机查看。

## 消息与声部

串口为 31,250 baud、8N1，输入经过两级同步。16 项事件 FIFO 缓冲音源背压。解析支持 Running Status、Note On 力度 0 作为 Note Off，以及穿插的实时消息。系统公共消息和 SysEx 会清除 Running Status。

| 消息 | 行为 |
| --- | --- |
| Note On / Note Off | 按通道和音符匹配，最多 32 个旋律声部。相同音符重弹会重新触发包络 |
| 力度 1～127 | 按当前琴键音量缩放，127 对应当前设定幅度 |
| CC64 | 每通道独立延音状态，值 ≥64 保持释放的音，值 <64 释放延音 |
| CC123～127 | 对应通道的 All Notes Off，遵循当前延音状态 |
| CC120 | 立即停止对应通道的音源声部，覆盖已进入释放段的声部 |
| CC121 | 复位该通道延音状态，并释放已经松开的延音声部 |
| System Reset | 清除 MIDI 声部与延音状态 |

所有通道使用屏幕当前选定音色。满复音时循环替换一个逻辑声部，原音符后到的 Note Off 会被识别为过期，避免关闭替换后的新音。FIFO 溢出或串口帧错误会请求明确静音并清理 MIDI 声部，随后可重新开始演奏。

Loop 记录已解析的演奏事件，包括力度与实际释放时刻。MIDI 的输入音高不套用自制琴板的白键交换表。共享效果器由现有效果设置控制，A 全部静音会同时结束效果尾音。

## 工程接口

- `fpga/midi_decoder.v` 负责消息边界和 Running Status。
- `fpga/midi_input.v` 负责接收、FIFO、通道／音符所有权、延音和统计。
- `fpga/performance_router.v` 为 MIDI 松键读取发声时保存的包络参数，立即停止事件使用零幅度。
- `fpga/display.cst` 将 AA19 固定为上拉的 3.3 V 输入。
- 输入模式 0 为 PC、1 为原单通道 ADC 测试、2 为自制 32 键扫描、3 为 MIDI。

二进制 UART 命令 37 使用现有 28 字节帧。请求 payload 的首字节 0 查询，第二字节 0／1 选择普通／扩展统计。首字节 1 设置输入模式，第二字节为 0～3。首字节 2 清统计，首字节 3 全部静音。普通回应包含模式、RX 高低、会话、功放就绪、延音、异常、保持数、队列深度、字节数、事件数、帧错误、溢出和最近音符。扩展回应的 payload[1] 最高位为 1，包含力度、通道、延音通道掩码、过期松键、替换次数和 MIDI 持有声部数。固件版本为 33。

## 验证入口

```powershell
python tests/midi/run.py
python tests/midi/run.py --physical-baud
python tests/midi/run_controller.py
python tests/midi/run_audio.py
python tests/navigation/run.py
python tests/navigation/run_integration.py
```

真实键盘验收应观察收包计数增加，试听单音、黑键、和弦、轻重触键、重复击键和全部松开。验收时记录实际码流与下载结果，串口仿真结果和真实琴键验证分别保存。

本版完成 63 项串行／分配检查，分别使用缩短的串口分频和实际 50 MHz／31,250 baud 配置。完整音频仿真解码了 553 个 I²S 样本，普通松键与踏板释放均能归零。控制器回归验证 MIDI 不随 PC 看门狗超时停止，实板进一步验证了 3.5 秒无电脑消息时 MIDI 会话继续保持、PC 模式按时关闭。板上还复测了菜单与 32／31 峰数字音频。

布局使用 51,113 / 59,904 Logic、25,820 / 60,780 寄存器、117 / 118 BSRAM 和 60 / 118 DSP。主时钟 Fmax 为 50.001 MHz，像素时钟为 49.743 MHz，USB 为 69.255 MHz。四个时钟域的建立、保持违例均为零。主时钟接近 50 MHz 目标，后续改动应重新执行布局与时序核对。
