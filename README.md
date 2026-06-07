# text-to-simple-video

把一段中文文本变成黑底白字、edge-tts 朗读的视频。每句依次出现，朗读完毕自动切下一句。

## 安装

需要 Python 3.9+ 和 `ffmpeg`（`brew install ffmpeg` / `apt install ffmpeg`）。

```bash
bash setup.sh
# 国内网络慢可以加 GitHub 代理：
#   bash setup.sh --mirror https://gh-proxy.com/
# 不想下开源字体（≈45 MB）：
#   bash setup.sh --skip-fonts
```

这会建 `.venv/`、`pip install -e .`（注册 `t2sv` 命令）、拉 3 个开源中文字体到 `fonts/`。

## 使用

```bash
source .venv/bin/activate            # 或直接用 .venv/bin/t2sv

t2sv sample.txt                       # 交互菜单 (10s 倒计时, 回车走默认)
t2sv --text "人生不是一场赛跑。"       # 直接传文字
t2sv sample.txt --no-prompt           # 全部走默认，不弹菜单
t2sv sample.txt --voice yunxi --resolution 1080p,vertical-1080
```

- **输入**：裸文件名会先去 `text/` 找；也支持绝对路径或 `--text`。
- **输出**：每次运行在 `video/` 下创建一个项目文件夹，里面按 `<voice>_<resolution>.mp4` 命名：
  - 默认文件夹名 `<YYYY-MM-DDTHH-MM>_<input-stem>/`，用 `-o myproject` 可自定义
  - 例：`video/2026-06-08T06-46_sample/yunxi_720p.mp4`
  - 多分辨率：`yunxi_720p.mp4`、`yunxi_vertical-1080.mp4`、...
- `t2sv` 在任何目录都能跑。
- 完整参数：`t2sv --help`。

## 语音（14 个预设）

| 区域 | key |
|---|---|
| 普通话 | xiaoxiao（默认）/ xiaoyi / yunxi / yunxia / yunyang / yunjian |
| 方言 | xiaobei（辽宁话）/ xiaoni（陕西话） |
| 粤语 | hiugaai / hiumaan / wanlung |
| 台湾国语 | hsiaochen / hsiaoyu / yunjhe |

`t2sv --list-voices` 看详情。`--voice` 也接受完整 edge-tts 名（如 `zh-CN-XiaomengNeural`）。

> 负号开头的值要用 `=` 写法：`--rate=-10%` / `--volume=-20%`（不然 argparse 会把它当 flag）。

## 分辨率（8 个预设，支持多选）

| 类别 | key | 像素 |
|---|---|---|
| 横屏 16:9 | `720p`（默认）/ `1080p` / `1440p` / `4k` | 1280×720 / 1920×1080 / 2560×1440 / 3840×2160 |
| 竖屏 9:16 | `vertical-720` / `vertical-1080` | 720×1280 / 1080×1920（抖音 / Reels） |
| 方屏 1:1 | `square-720` / `square-1080` | 720×720 / 1080×1080（朋友圈 / IG） |

多选时 TTS 只跑一次复用音频，每个分辨率独立出一份 mp4：

```bash
t2sv sample.txt --resolution 720p,vertical-1080,square-1080
t2sv sample.txt --resolution all         # 一次出 8 个
```

交互菜单同样支持 `1,3,5` / `1-3` / `all`。

## 字体

启动时扫描两类来源：

1. **macOS 系统字体**：Hiragino W3/W6、STHeiti Light/Medium、Songti Light/Regular/Bold/Black
2. **`fonts/` 目录下任意 `.ttf/.ttc/.otf`**（`fonts/download_fonts.py` 会拉霞鹜文楷、思源黑体、思源宋体）

默认选项由 `text_to_video.py` 顶部的 `DEFAULT_FONT_KEYS` 决定（按顺序找第一个存在的）。改默认调整这个列表即可。

苹果系统字体授权仅限本机使用，**不能 redistribute**，所以仓库里不放苹果字体。想用更多苹果字体（楷体 Kaiti、圆体 Yuanti 等），打开「字体册」下载后用 `--font /path/to/font.ttc` 指定，或把文件软链到 `fonts/`。

## 目录结构

```
text-to-simple-video/
├── setup.sh                       # 一键安装
├── pyproject.toml                 # 注册 t2sv 入口
├── LICENSE                        # MIT
├── text_to_video.py               # 主脚本
├── fonts/download_fonts.py        # 拉开源字体（产物 gitignore）
├── examples/render_font_samples.py # 重生字体预览图（产物 gitignore）
├── text/                          # 默认输入目录（只跟踪 sample.txt）
└── video/                         # 默认输出目录（gitignore 全部产物）
```

## License

MIT — 见 [LICENSE](LICENSE)。

## 工作原理

```
文本 ─► 切句 ─► [edge-tts → MP3]   ─► ffmpeg 拼成短 clip
              [Pillow  → PNG ]      (clip_dur = audio + 0.4s 静音)
                                  ─► ffmpeg concat → 最终 mp4 (H.264 crf=18 + AAC)
```

## 已知限制

- 切句只针对中文标点；纯英文不按 `.` 切（需要的话改源码顶部的 `SENTENCE_END_RE`）。
- edge-tts 在线 API，需要网络。
- 交互倒计时基于 `select(stdin)`，Windows 不支持；请用 `--no-prompt`。
