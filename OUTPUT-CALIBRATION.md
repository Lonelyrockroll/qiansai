# v28 板载 DAC 输出校准

当前板卡为 Tang Mega 60K NEO。音乐合成、数字录音与标准 I²S 共用原有的有符号 PCM。板载 PT8211 的交流耦合输出单独增加直流偏置，使小音量持续音使用另一段转换码。正式版上电偏置为 1637；v27 为 683。只在功放关闭、未保持演奏且无活动音符时可以改校准值。运行时调整只保存在 SRAM。

## 耳机口测量

Tang 耳机输出通过 Ampero II Stomp FX LOOP RETURN 接入 USB 5/6；使用相同输入增益。以 2% 对应的力度持续奏 C4，两种偏置下的板内 24,576 个数字采样均通过同一 CRC32 校验，但耳机口录回的谐波不同。下表为二至八次谐波幅度平方和开根号与基频幅度之比，取两个声道中较大的数值。

| 音符与力度 | v27，683 | v28，1637 |
|---|---:|---:|
| C4 · 1% | 0.91% | 1.20% |
| C4 · 2% | 11.08% | 0.72% |
| G4 · 2% | 10.86% | 0.79% |
| C4 · 4% | 6.19% | 0.47% |
| C4 · 7% | 4.56% | 3.79% |

2% 力度下，修正后 8 秒 C4 的二次至 20 kHz 内全部谐波合计仍约 2.05%，可以听到少量随音高变化的毛边。功放开启且音乐 PCM 为零时，这次采集系统的 20 Hz～20 kHz 背景约为 −88 dBFS。以上模拟测量包含板上转换、放大和 RETURN 采集链，在本块板和本次接线下得到。

[修正前连续 C4](tests/output_trim/results/C4-actual-before-continuous-8s.wav) · [修正后连续 C4](tests/output_trim/results/C4-actual-after-continuous-8s.wav) · [逐声道测量](tests/output_trim/results/measurements.json)

## 工程

打开 `fpga/synth_display.gprj`。完整布局检查通过，实板临时下载及独立 JTAG 回读 User Code 为 `0x0000729A`。上电即读回 1637，正式码流验收期间没有发送偏置写指令。[SRAM 码流](firmware/clean-output.zip) · [布局与校验报告](firmware/output-trim-build.json)

UART 命令 30 的操作 0 读取偏置，操作 1 写入随后两个字节表示的无符号小端数，取值 0～4095。超范围或功放未关闭的写操作会被拒绝。常规演奏不需要发送此命令。运行 `tests/output_trim/tb_output_trim.v` 的串行引脚测试可检查 PT 两声道实际数据、饱和与帧边界，以及原始 I²S 数据。
