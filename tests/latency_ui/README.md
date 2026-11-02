# 延迟结果页验证

从仓库根目录运行 `node tests/latency_ui/test_browser.cjs`。需要 Node.js、Playwright 和 Chromium。在 Windows 上默认使用 Edge，可通过 `LATENCY_BROWSER` 指定已安装的浏览器通道。若 Playwright 由共享运行时提供，将其 `node_modules` 目录加入 `NODE_PATH` 后运行。

回归启动独立的本地 HTTP 测试服务，在真实浏览器中检查令牌、板内序号去重、不同测量段和参数的统计、单路 MARK / 同步双通道 CSV 请求、失败反馈、T₀/T₁ 标线、阈值线、放大与展开波形、WAV、390 像素宽显示。浏览器试验使用明确标注的测试夹具，不打开板卡、示波器或声卡。

`results/scope-fixture.png` 和 `results/mobile-fixture.png` 是测试夹具界面。另已对本机实际运行服务执行只读浏览器检查，`results/live-digital.png` 与 `results/live-mark-focus.png` 显示保存的 H15 / C4、MARK 脉宽、起止标记、归档波形说明。实际检查只读取已存记录，未通过页面发起设备读取或导入。详情见 `real-readonly-validation.json`。
