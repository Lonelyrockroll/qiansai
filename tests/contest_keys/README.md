# TKAK 与实体键位回归

运行 `python tests/contest_keys/run.py`。Java 用安卓 App 的编码器生成请求。仿真向真实 `bt_console` RX 送入 8N1 串口波形，独立在 TX 引脚按位中心取样，把返回字节交给 App 的 `StreamReader`。使用 50 MHz 仿真时钟和 434 个时钟周期的位宽。

覆盖 `~J` 能力查询、初始音高、H15/H16 互换、同包重发、不同琴键查询、忙时拒绝、忙状态解除后同包成功、恢复默认、越界、错误长度和 CRC。每个请求后轮询实际 `scan_key` 输入，核对 32 个 `pitch_key` 输出。`layout_safe` 的两种状态由测试主动驱动。本项证明串口至映射表及扫描输出。物理动作、键盘扫描和模拟音频输出属于独立实物验收。

结果在 `results/validation.json`。`key-wire.hex` 为 15 个 FPGA TX 回包，`key-requests.hex` 为对应的 14 个 Java 二进制请求，另一次响应由文本 `~J` 触发。
