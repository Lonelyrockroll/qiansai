# PDF 单页缓存与蓝牙协议 RTL 验证

从工程根目录运行：

```powershell
python tests/score_fpga/run.py
```

需要 Python 3 和 Icarus Verilog。测试将生产 RTL 复制到临时目录再编译，以报告内 SHA256 标识实际使用的源码。

`tb_score.v` 使用 Android Java 编码器生成的真实 PDF 第 1 页：65536 个原始字节、13464 个 RLE 字节、845 个完整请求，包含多次 255→0 序号回绕。BEGIN、一个 DATA 和 COMMIT 分别额外重发，要求回复逐字相等且不重复写入。提交后从共享 RAM 的系统时钟端口及异步像素时钟端口逐一核对全部 32768 个字，验证地址和高字节先写的位图格式。

其他覆盖包括：RLE 的 count/value 跨包；零长度 run；错误 offset、压缩长度、图像尺寸；原始图不足或超过 65536 字节；坏包 CRC16 和坏图 CRC32；失败帧重试；捕获忙或有结果时拒绝 BEGIN；先等待视频隐藏再写旧页面；本地隐藏/显示/清除，以及清除等待期间保留 RAM 占用；上传期间忽略本地清除；上传和外层帧超时；视频隐藏超时仍保持 RAM 占用，待实际隐藏后释放；对应 ~P/~G 的两种 capability probe 回复及录音互斥。

释放页面后再运行原 PCM 采集，核对样本、计数和 CRC；另外实例化没有连接新曲谱输入的旧式 `pcm_capture`，确认 `SCORE_SHARED=0` 默认路径不受悬空输入影响。旧演奏指引 179 条请求和 24 个 Android MIDI 请求也同步回归。

`results/score-java-acks.hex` 是对应 845 个 Java 原始请求的 20280 字节纯 TPAK 回复，不含测试注入的重复、错误或能力查询。`tb_score-acks.hex` 保留全部回复。`validation.json` 记录结果及源码指纹。这些是 RTL 仿真证据，不声称手机或实板已经完成显示验收。

## 物理存储

`score_capture_ram.v` 只有两个物理端口：端口 A 的系统时钟读写共用地址（PCM 写、曲谱写、PC 读互斥），端口 B 为像素时钟读取。没有第三个逻辑读端口，也没有时钟复用。

在 GW5AT-LV60PG484AC1/I0 上以 Gowin EDU V1.9.11.03 真实布局布线，32768×16 共享 RAM 占 32 块物理 DPB BSRAM，与被复用的原 PCM 缓存相同。结果在 `results/shared-memory-physical.{txt,json}`，不是只引用综合阶段的逻辑 primitive 计数。独立映射测试未添加工作频率约束，整机时序以顶层构建报告为准。

## 接口要点

顶层必须以 `pcm_capture #(.SCORE_SHARED(1))` 接上曲谱写口和像素读口。`score_reserved` 在有效、上传中、或尚未完成视频隐藏时保持高电平，拒绝 PC 采集重新占用。传给 transport 的 capture_busy 应包括同周期 PC arm 意图，防止 BEGIN 与 arm 同时获得授权。

BEGIN 会丢弃旧页，先撤销显示请求，等 `score_video_visible=0` 才允许写入；只有完整 RLE、长度及原始 CRC32 通过 COMMIT 才重新请求显示。CLEAR 同样等待视频隐藏后释放 RAM。隐藏仅撤显示请求，保留页面。新页面断电丢失。

协议请求沿用 28 字节 A5 47 帧；曲谱 op16..20 返回 TPAK，演奏指引 op0..4 保持 TGAK。状态码：0 成功，1 CRC 错误，2 未知命令，3 参数/编码/越界错误，4 正忙，5 上传状态/offset/完整性/超时错误。已分派命令的正忙回复不缓存，便于条件恢复后用同包重试；外层 CRC16 或封装错误也不缓存。其余已执行命令的重复包直接重发缓存回复，不重复操作。
