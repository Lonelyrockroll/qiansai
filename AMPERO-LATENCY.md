# 用 Ampero 录下实体触键的声音

将 Tang 耳机输出通过合适的音频线接到 Ampero II Stomp 的 FX RETURN，再把 Ampero 用 USB 连到电脑。此前的实录由 Hotone ASIO 的 USB 输入 5/6 采集左右声道。保持 Ampero 的返回通道处于原始、无门限和无效果的录音路由，先在 Tang 上选好琴键扫描和演奏状态，检查轻按 C4 时 Ampero 有输入电平。

在本工程根目录执行以下命令。本机已有 Python、NumPy 和带 ASIO 支持的 sounddevice。其他电脑还需安装 Hotone 驱动；若没有 Python 依赖，可先执行 `python -m pip install numpy sounddevice`。

```powershell
python tools/capture_latency_ampero.py devices
python tools/capture_latency_ampero.py record --name "实体第15键 C4" --audio-channel 5 --seconds 5
```

`devices` 列出本次真正可用的 Hotone ASIO 输入，空列表表示应先检查 Ampero 电源、USB 线和驱动。录音开始后先保持安静，约一秒后按命令行提示只击键一次。工具在相同声卡时钟上保存 ASIO 5 和 6，结果放在 `output/latency/audio/ampero_…/`。其中有未经归一化的原始 WAV、全采样时间序列 `samples.csv` 和可用于界面显示的 `record.json`。音头时间是所选输入相对于 WAV 第一个样本的时间。耳机的左右声道都只含音频，这种接法的 `latency_ms` 为 `null`。

如有第二路独立的模拟动作参考，可把已经适配好电平的触键拾振器输出接到另一个 Ampero 模拟输入。例如 ASIO 5 只收 Tang 耳机声音，ASIO 6 单独收拾振器。确认两路分别录到各自的信号后再执行：

```powershell
python tools/capture_latency_ampero.py record --audio-channel 5 --reference-channel 6 --reference-label "琴键接触拾振器" --name "C4 动作参考与耳机输出"
```

普通音频输入只接与设备相容的模拟信号。MARK、TTL、裸霍尔输出和电源轨不要直接接 Ampero。拾振器测得的是其自身触发相对琴声的时间差，换能器、安装位置、前置电路和输入滤波都可能引入偏差。霍尔阈值至模拟输出的正式两通道示波器测法见工程现场验收说明。

两种录音模式都使用 0.25～0.75 秒的安静区估计基线，寻找第一次连续三点越阈的首样本，保留实际采用的归一化幅度门限。可用 `--audio-threshold-dbfs` 或 `--reference-threshold-dbfs` 指定固定门限，便于比较不同力度。输入溢出、近满幅、提示前越阈或缺少有效音头时，结果会写明原因。采样间隔只给出声卡对两个时间点的离散测量界限。

历史示例来自 2026 年 10 月 9 日 v8 钢琴 C4 的原始 Ampero ASIO 5/6 实录。当时先发了音符再开录，界面将它标为“历史 Ampero 录音 · 非本次试验”，只展示录音波形。[档案及来源](output/latency/audio/history_20261102_174847_746491/record.json)
