# v29 · 减轻持续音的高次谐波

原 v28 已减轻低阶失真，但在相同 C4 的耳机口录音里，从二次到 20 kHz 的全部谐波合计仍接近基频的 2.05%。试听者指出带着这些谐波的片段更接近实物上听到的“嗞”。因此本次使用全频段的随音谐波与剩余背景分别评估。

正常演奏时，FPGA 每秒生成 48,828.125 个音乐采样。板载 PT8211 的更新率为 195,312.5 Hz。一个音乐采样分四个子帧发送，在每个子帧分别加上 1717、1437、1613、1539 码偏置，使转换落在不同的码值区域。平均偏置为 1576.5 码。两声道使用相同顺序，保持音程、同步及包络。USB 录音、板内 PCM 和标准 I²S 仍以原格式工作。[Princeton Technology PT8211 数据手册](https://www.princeton.com.tw/Portals/0/activeforums_Attach/PT8211%20V1.7_E.pdf?ver=I8v0SNPIQri_LxlOI2sp7w%3D%3D)

## 实测

Tang 耳机口接 Ampero FX RETURN，USB 5/6 以相同增益录制。表中数字为二次到 20 kHz 内各次谐波的幅度平方和开根号，相对基频的百分比，取两声道中较高值。单独提高更新率时，2% C4 仍约 1.97%。采用交替偏置后才获得本表中的改善。

| 单音 | 上一版 v28 | 本版 v29 |
|---|---:|---:|
| C4 · 1% | 3.09% | 1.07% |
| C4 · 2% | 2.05% | 0.58% |
| G4 · 2% | 2.13% | 0.61% |
| C4 · 4% | 1.13% | 1.18% |
| C4 · 7% | 4.29% | 2.69% |

2% C4 的基频电平前后相差约 0.02 dB，24,576 个板上数字采样的 CRC32 相同。计入其他残余信号后，该音符的总失真加噪声从 2.47% 降到 1.37%。空闲时 20 Hz～20 kHz 的采集背景都约为 −88 dBFS。上述数字描述该板在本次接线与力度下的表现。钢琴 C4 的 4,096 个 PCM 样本与 v27 逐点一致。[测量记录](tests/output_trim/results/quad/performance.json) · [钢琴回读对照](tests/output_trim/results/quad/piano_match.json)

以下两段都是同一耳机口的真实录音，各连续 8 秒。从两次采集的中段截取并施加相同试听增益，仅首尾各做 12 ms 渐变。[上一版 v28](tests/output_trim/results/quad/long_v28-actual-8s.wav) · [本版 v29](tests/output_trim/results/quad/long_best-actual-8s.wav)

## 使用

当前板上的 SRAM User Code 为 `0x00009269`。复现时可用 Gowin 打开 `fpga/synth_display.gprj`，或直接临时下载压缩包中的 `quad-output.fs`。上电默认即为四子帧交替模式。系统时钟目标 50 MHz，布局报告 Fmax 50.070 MHz；全部约束时钟 setup/hold 通过，保留 PR1014 系统时钟布线警告。[v29 码流](firmware/quad-output.zip) · [布局与校验报告](firmware/quad-output-build.json)

校准命令 30 保留原有读／写偏置操作，并支持操作 2 写入模式 0、1 或 2，依次为原速固定偏置、四倍固定偏置、四倍交替偏置。改变偏置或模式前须关闭功放并释放所有音符；默认演奏不需要发送校准命令。串行管脚测试见 `tests/output_trim/tb_quad.v`。
