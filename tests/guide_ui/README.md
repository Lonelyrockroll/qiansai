# HDMI 指引界面验证

这些测试直接仿真 `fpga/panel_renderer.v` 的 RGB 输出，不使用绘图程序重画界面，也不会重新生成或改写稳定 RTL/ROM。

## 运行

需要 Python 3、Pillow（`python -m pip install Pillow`）和 Icarus Verilog（`iverilog`、`vvp`）。从仓库根目录运行：

```powershell
python tests/guide_ui/run.py --check-only
python tests/guide_ui/run.py --render-only
```

省略两个选项会依次执行回归与整帧渲染。若 Icarus 不在 PATH，可指定 `--iverilog <编译器路径> --vvp <运行时路径>`，或设置 `IVERILOG` / `VVP` 环境变量。脚本按自身位置查找仓库和 `fpga/`，不依赖原开发者的盘符、临时目录或字体安装路径。

默认输出至已忽略的 `tests/guide_ui/.work/`；可用 `--output-dir` 改变位置。`.vvp` 和中间 PPM 不作为版本化证据提交；PPM 默认在转换 PNG 后删除。每页需要仿真 614,402 个像素时钟。

## 覆盖范围

- `check_tb.v`：BCD 上界 65535、更新到 0/1、事件数 512、索引 511、Loop 时长 800；新弹/延音配色、下一组提示、真实琴键正确/偏离边框、鼓组页保持独立琴键反馈；菜单第 10 项（focus 9）高亮。
- `render_tb.v`：分别输出琴键页和鼓组页的真实 1024×600 RGB。固定场景包含 C4/E4/G4 目标、D4 偏离实按、下一组提示、时间 `012.34 / 048.20 秒` 及 focus 9。
- `verify.py`：检查 3 个字体银行分别为 1024×16 位，2970 个有效字逐行等价于保留的旧打包字体表，省略的第 16 行全零；将新 PNG 与已验收 PNG 逐像素比较。

`fpga/compact_ui_font.hex` 仅作为旧 16 行打包参考；当前 renderer 实际加载 `compact_ui_font0.hex`、`compact_ui_font1.hex`、`compact_ui_font2.hex`。字符串 ROM 和三周期像素流水线保持不变。

## 已验收证据

`results/guide.png`、`results/drums.png` 是 2026-11-02（UTC+08:00）的真实 RTL 仿真输出，非示意图。两页各比较 614,400 像素，差异都是 **0**。原始生成时间、逐页 RGB 哈希和字体/字符串验证见 `results/verification.json`。

- 压缩前 renderer SHA256：`c779969a4e78134992cf61ad40a664d3ebd3b40ee514ee5b9018221b7d794ded`
- 3-bank renderer SHA256：`508ccd186332959cf61bd8972edbf555cc50b03ff4f82f0976c96a9b5152b591`

旧 baseline RTL 和大体积 PPM 没有复制进测试目录；无损检查时的 baseline hash 与零差异结果已记录。日后复现以这两张已验收 PNG 的像素为基准，输出新的报告到 `.work/verification.json`，不要覆盖 `results/`。

## 资产生成器

`tools/generate_guide_panel.py` 的输入只有代码内的文案/布局和 Microsoft YaHei 字体 `C:/Windows/Fonts/msyh.ttc`；临时目录仅由 `tempfile` 在可选预览期间自动创建，并非必需的外部输入。要逐字节再生成相同 ROM，应使用相同字体文件；运行本目录的渲染/回归测试不需要安装该字体，因为测试直接读取仓库内已生成 ROM。
