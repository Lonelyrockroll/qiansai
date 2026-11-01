# 曲谱视频通路独立验证

这组测试实例化实际 `score_renderer.v`、`score_capture_ram.v` 和 `video_timing.v`。没有使用截图重绘、假RAM延迟或与DUT相同的逐行累加算法作为期望值，也不改动生产源码。

## 复现

需要 Python 3、Pillow 和 Icarus Verilog。从仓库根目录运行：

```powershell
python tests/score_video/run.py
```

Icarus可由PATH查找，也可用 `--iverilog <路径> --vvp <路径>` 或环境变量 `IVERILOG` / `VVP` 指定。默认中间产物位于 `.work/`（已忽略）；`--output-dir` 可另选目录。测试读取仓库已有的 `output/pdf/score-demo/page-01.bin`，**不会重新生成PDF**。

## 验证内容

1. **独立整帧寻址与像素期望**：对每个输入有效像素直接计算 `source_y=floor(y*512/600)`，与实际读地址比较；用MSB左、1=黑的独立位提取形成RGB期望。非平凡地址图样填充整个真实RAM，连续验证5帧共3,072,000个有效像素，包含初帧、所有行首/行尾、最后一行和帧间重置。
2. **异步请求与垂直消隐生效**：请求在时钟边沿之外改变；`visible` 只能在 `y=600,x=0` 的 `frame_start` 锁存。五帧预期可见状态是 `[0,1,0,0,1]`，其中第三帧末尾距离锁存过近的请求因两级同步器而延后一个完整帧生效。
3. **真实双时钟RAM**：像素端使用真实同步读；系统端另用不同频率时钟持续读地址图样，确认系统读数据也在时钟后更新。
4. **实际示范页**：原始 `.bin` 通过高字节在前装入16位RAM，连续验证2帧共1,228,800个有效像素。导出第二帧真实RTL RGB为PNG，逐像素对照既有 `page-01-restored-600.png`。
5. **与原面板合成时序**：单独实例化真实 `panel_renderer.v`，使用其内置测试图产生确定RGB，与曲谱模块共同驱动任意变化的HS、VS、DE及坐标。逐周期核对原面板RGB/HS/VS/DE、曲谱RGB/`select_page` 和最终二选一RGB均为相同三阶段像素延迟。

`run.py` 会保存日志、实际RTL PNG及 `verification.json`，报告包含生产源码SHA256、测试数量、零像素差异结果和执行时间。运行前后生产源码hash必须一致，避免把不同版本的结果混为一份证据。

## 格式约定

位图1024×512，按行排列，每行128字节，字节最高位为最左像素；RAM每字16位，先读取原始数据的高字节。输出画面1024×600，以 `floor(y*512/600)` 最近邻选行。手机的PDF→512行渲染与这里的512行→600行显示是不同步骤；本测试从手机传输格式开始验证FPGA显示。

## 独立 CDC 所有权测试

```powershell
python tests/score_video/run_ownership.py
```

此入口只跑跨时钟保护，不重复430万像素整帧仿真。它实例化生产 `synth_display_top`、`bt_console → guide_transport → score_store`、`score_renderer` 和 `pcm_capture → score_capture_ram`。测试台提供已解析的命令字段、两路时钟和缩短的垂直消隐；Icarus `-i` 只省略此测试不使用的外设IP。保护逻辑、前向/返回两级同步器、存储器所有权及真实RAM写端口均直接使用生产代码。有效旧页状态是预置测试前提，SHOW/HIDE/BEGIN/CHUNK命令则真实执行。

系统时钟50 MHz，像素时钟约49 MHz，以1 ns间隔扫描20个起始相位。每个相位测试：①一个系统周期的SHOW后立即BEGIN，②SHOW后HIDE再BEGIN，③SHOW后BEGIN但无迟到场边界。在前两种情况中把帧边界放在SHOW前向传播窗口，使已经撤回的显示请求仍在像素域锁存；故意让这帧保持超过32系统周期，检查此时返回的 `visible` 仍持有RAM。第三种情况只靠32周期保护，BEGIN在第33个周期才答复。每次都实际发送CHUNK并写出`0xA5A5`，断言共享RAM写端口只会在前向同步器、实际可见、页面选择和所有权全部清零后触发。

本版60例全部通过；40例确实触发迟到可见，32周期后仍由返回同步信号继续保护21或22个采样周期。测试还仅在仿真中强制去掉保护作为反例，此时断言如预期失败，说明测试能检出旧竞态。详见 `results/ownership.json`。这是数字时序仿真，不模拟触发器的模拟亚稳态。
