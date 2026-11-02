# v32 曲谱与现场观察页控制器回归

运行 `python -X utf8 tests/score_controller/run.py`。测试只替代 `uart_rx` 的字节输出，不强制控制器内部状态；所有应答均从 `uart_out` 的实际 8N1 波形独立解码，再验证 28 字节包头、序号、固件版本、操作码、异或校验和载荷。

当前控制器通过 457 次断言、80 次串口请求与应答。原有曲谱用例覆盖 op32 状态和显示、隐藏、清除，op33 六字读取与边界，读取期间和末字锁存后页失效，原 op23 PCM 读回，采集忙和曲谱占用时拒绝 op21，同周期抢占、短按退出与反压，以及手机先退出时不误执行底层菜单。控制器源码 SHA256 与日志见 [validation.json](results/validation.json)。

观察页从 LIVE 短按 B 时分别单独输入旧 held、活动声部、效果尾音、效果更新未完成，以及多项同时存在。暖机接管只发一个 `monitor_fade`，保持 `amp_hold` 和本地会话，等 `engine_cleared` 才进入 32 音模式。测试还覆盖等待期间再按 B、切至 31 音、向前和向后移动缺口及 A 静音退出。冷启动与暖机空闲可直接进入 32。

Loop 正在播放、录制或待录时，测试分别检查控制器仍停在 LIVE，未发出清音、panic 或 Loop 命令。已停止的层允许接管，对应的层数和事件数仍能通过 op14 读回。等待清音时也分别模拟按 A、PC 静音、手机显示 PDF 和 USB 键盘断开，随后到达的清音完成脉冲不会重新启动演示。Loop、功放与路由状态在本项测试中由控制器外部测试输入驱动，整条音频链的实际反应以独立整机验证为准。

安卓侧另以 `ScoreAckTest.java` 对 FPGA 仿真输出的 845 个 TPAK 回包逐个核对，见安卓工程 [score_validation.json](../../realtime_synth/android_recorder/score_validation.json)。这些为 RTL/JVM 联合验收，不等同于手机与板卡的实物联调。
