# 两页白键曲谱示范

`../score-demo.pdf` 是本项目重新排版的传统《小星星》旋律，非网络乐谱截图，也没有虚构出版物来源。它使用 C 调、4/4 拍，包含完整 12 小节，分两页各 6 小节；全部旋律为 C4、D4、E4、F4、G4、A4，处于本系统 C2-F6 的白键范围内。

每个数字是一拍，`-` 是上一音再延长一拍。完整旋律为：

```text
第1页：
1 1 5 5 | 6 6 5 -
4 4 3 3 | 2 2 1 -
5 5 4 4 | 3 3 2 -

第2页：
5 5 4 4 | 3 3 2 -
1 1 5 5 | 6 6 5 -
4 4 3 3 | 2 2 1 -
```

这是用于验收“手机传谱、板卡全屏读谱、手机翻页”的曲谱文件。PDF 位图不会自动发声，也不等于 MIDI 键位指引数据。

## 文件和格式

- `page-01-original.png`、`page-02-original.png`：从 PDF 实际渲染的 1024×600 原尺寸预览。
- `page-XX-storage.png`：原页面无裁切，Y 轴压缩到 512 后的渲染图。
- `page-XX.bin`：65536 字节的黑白位图，1024×512，逐行存储，字节最高位为最左像素，1=黑，0=白，每行128字节。
- `page-XX.rle`：依次为无符号字节 `count,value`，count取1..255，无文件头。解码后必须恰为65536字节。
- `page-XX-mono-512.png`：由原始位图解码得到的黑白图。
- `page-XX-restored-600.png`：按 `source_y=floor(display_y*512/600)` 恢复至1024×600，供检查板上显示效果。
- `metadata.json`：旋律、音名、图形尺寸、CRC32、SHA256及编码规格。
- `validation.json`：实际PDF页数、尺寸、中文文字及二进制回环校验记录。

黑白阈值采用 `(77*R+150*G+29*B)>>8 < 180`。这与安卓处理约定一致；此处用 Poppler，手机用 Android PdfRenderer，抗锯齿实现可能产生少量边缘像素差异，不应要求不同渲染器逐字节相同。蓝牙接收端对每次实际上传的数据验证 CRC32。

| 页 | 原始字节 | RLE字节 | 原始位图CRC32 |
|---|---:|---:|---|
| 1 | 65536 | 13464 | ECF5A696 |
| 2 | 65536 | 13518 | C3C3BF39 |

PDF同内容副本已放入 `realtime_synth/android_recorder/src/main/assets/score-demo.pdf`，用于安卓示例按钮。两个PDF的SHA256相同。

## 复现

依赖 Python 3、ReportLab、Pillow 和 Poppler `pdftoppm`。在仓库根目录运行：

```powershell
python tools/generate_score_demo.py
```

可用 `--font <中文TrueType字体>`、`--pdftoppm <可执行文件>` 指定依赖。默认字体是 Windows 微软雅黑；不依赖原作者临时目录。生成器会自动复制安卓资产；仅制作PDF时可加 `--no-copy-asset`。

为了可复现，ReportLab使用 `invariant=1`，所以PDF内置创建日期固定；实际验证时间见 `validation.json`。使用不同字体版本或渲染器版本可能改变像素和CRC，生成器会重新计算对应元数据。

本版已逐页查看原PDF渲染和最终恢复图：无黑框、缺字、乱码、遮挡或裁切；页码、横线延音及B键返回提示均清楚。
