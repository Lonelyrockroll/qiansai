# 电脑观察工具验证

`python tests/pc_analysis/run.py` 读取已采的实板样本，核对随附 CRC32、SHA256 和采集参数，再检查三个场景的完整频点集合。另用模拟 UART 验证 PDF 占用、已有冻结/在录/待触发结果、Loop 录制或待录、错误编号、CRC 失败和自身触发超时等保护逻辑。此步骤依赖 NumPy 和 Pillow，不访问板卡。

`python tools/package_pc_audio.py` 用明确的文件清单制作 `output/Tang-PC-Audio-Tools.zip`。发布前会在仓库外解压，在 `python -S` 下启动包里的标准库页面，检查三个 WAV 入口，再在隔离目录执行离线渲染并核对关闭第 17 音的峰表。包里不装 Python、第三方库、浏览器缓存或其他录音。

`python tests/pc_analysis/browser_check.py --kit output/Tang-PC-Audio-Tools.zip` 需要 Playwright Python 包和本机 Chromium。用 `--browser` 可指定浏览器可执行文件。测试只开独立浏览器实例，使用 Chromium 的虚拟录音设备与已知 32 音 WAV。它验证页面打开时不采音，读取设备名称后临时音轨结束，随后明确选中设备才启动观察，停止后所有音轨都释放。同一页面还经过三个已采实板档案的循环回放，四张 Canvas 都有输出。`results/browser-validation.json` 标出本次实际浏览器分析采样率及回放峰频点，外部声卡模拟链路没有在本项试验中实测。

当新一轮板测完成，依次重新运行上述三个命令，再运行 `python tests/pc_analysis/check_bundle.py --expected-code 0x实际值 --newer-than tests/contest_board/intermediate-C69B/spectrum.json`。核对当前 `after_jtag.log`、三段采集编号/首帧/SHA256、ZIP 中原始数据、报告和峰表，以及浏览器测试实际展开的 ZIP 哈希。所有检查通过后写入 `results/package-validation.json`。
