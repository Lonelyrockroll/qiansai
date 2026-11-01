# v31 曲谱控制器回归

运行 `python -X utf8 tests/score_controller/run.py`。测试只替代 `uart_rx` 的字节输出，不强制控制器内部状态；所有应答均从 `uart_out` 的实际 8N1 波形独立解码，再验证 28 字节包头、序号、固件版本、操作码、异或校验和载荷。

冻结版本通过 144 项断言、28 次串口请求/应答。覆盖 op32 状态和显示/隐藏/清除、op33 六字读取与边界、读取期间和末字锁存后页失效、原 op23 PCM 读回、采集忙和曲谱占用时的 op21 拒绝、同周期抢占、短按退出与反压，以及手机先退出时不误执行底层菜单。基准控制器 SHA256 与实际日志见 [validation.json](results/validation.json)。

安卓侧另以 `ScoreAckTest.java` 对 FPGA 仿真输出的 845 个 TPAK 回包逐个核对，见安卓工程 [score_validation.json](../../realtime_synth/android_recorder/score_validation.json)。这些为 RTL/JVM 联合验收，不等同于手机与板卡的实物联调。
