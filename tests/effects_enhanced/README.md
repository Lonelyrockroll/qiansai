# FX2 验证

从仓库根目录运行，Python 需要 NumPy，RTL 使用 Icarus Verilog。

```
python tests/effects_enhanced/verify_fx.py
python tests/effects_enhanced/test_presets.py
python tests/effects_enhanced/generate_phrase.py
python tests/effects_enhanced/listen.py
```

`verify_fx.py` 在工作区 tmp 中重建测试台，逐样本对照 227,051 个输出。`reference.py` 是增强版模型，`baseline_reference.py` 保留旧效果的整数模型。`generate_phrase.py` 使用生产音源 HDL 生成共同输入；`listen.py` 将同一音源输入交给新旧效果，所有文件采用同一个增益。

`switching.v` 与 `transitions.v` 分别验证持续音切换和清除、尾音、禁音。编译时顶层分别为 `switching` 与 `tb`，共同源文件为 `fpga/audio_effects.v`、`fpga/chorus_lfo.v`。结果见 `results/verification.json`。

`board_check.py` 会临时静音并操作实板，通过板载菜单动作与上位机配置函数读取真实参数，再采集最终 PCM。它要求已加载 FX2、没有待保留的录音和 Loop，并在结束时恢复琴键配置、选择增强混响、保持静音。已完成的记录在 `board/`，JTAG 回读为 `0x000079A5`。同目录的 `http_presets.json` 额外验证了正在运行的上位机 HTTP 入口。
