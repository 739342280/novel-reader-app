# 📖 小说智读 (NovelReaderApp)

![Version](https://img.shields.io/badge/version-v0.3.19-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-green.svg)
![Flet](https://img.shields.io/badge/flet-0.84.0-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android-lightgrey.svg)

**小说智读** 是一款基于 [Flet](https://flet.dev/) (Flutter 引擎) 构建的现代化、跨平台本地小说阅读器。它不仅拥有媲美商业级 App 的极致排版与沉浸式交互质感，更深度融合了大语言模型（LLM），为你提供“伴读式”的 AI 剧情解析体验。

> *“将代码的极简主义，注入到每一次指尖翻页的沉浸之中。”*

---

## ✨ 核心特性 (Core Features)

### 📚 智能本地书架管理
* **极速本地解析**：毫秒级导入大体积本地 `.txt` 文本，多重编码（UTF-8, GBK 等）自动嗅探防乱码。
* **双轨目录状态机**：强大的底层正则引擎，精准剥离「卷名」与「章名」，在书架卡片与阅读页顶部提供双层显性导航。
* **无损导出与重命名**：支持书籍的长按重命名管理，并提供一键无损导出副本至本地设备。

### 🎭 商业级 UI 质感与交互
* **全局系统级色彩联动**：完美接管日/夜间模式生命周期。日间模式下，沉浸式菜单智能提取并融入背景底色（如牛皮纸底色）；夜间模式则强力压制所有高亮彩色，强制转换为极致纯黑与护眼灰字，深邃且专注。
* **高阶视觉状态反馈**：告别生硬的色块切换。阅读背景选择引入轻盈的**“弥散发光阴影”**交互，字体选择应用**“自适应微光包裹”**算法，零结构破坏，尽显高级。
* **如丝般顺滑的转场**：彻底掩盖底层引擎排版跳变，引入定制化 `300ms` 文本淡入（Fade-in）动画。

### ⚙️ 极客级排版与引擎调优
* **全景排版控制**：支持实时微调字号、**字距**、行距、段距，内置（默认、汉仪旗黑、中宋、正圆）多套高阶中文字体自由切换。
* **防抖像素级进度追踪**：摒弃粗糙的按章算进度，独创**全文字符绝对偏移量算法**，进度百分比实时包含“章内像素级滑动占比”，精确到 `0.1%` 防抖刷新，零性能损耗。
* **钢铁般的存盘机制**：移动端拦截系统 `Lifecycle` 状态防杀后台；PC 端独创带“硬盘防磨损比对”的 5 秒静默轮询保存。随时强退，随时精确到上一秒的像素级续读。

### 🤖 大模型 AI 智能伴读
* **全流式极速响应**：配置专属 API Key（默认适配 DeepSeek，兼容 OpenAI 格式），一键呼出 AI 面板。
* **定制化多维解析**：通过系统级 Prompt 锁定输出质量，智能剖析本章的：`一句话概括`、`情节脉络`、`人物弧光`、`文笔赏析` 与 `悬疑钩子`。
* **本地摘要持久化**：AI 生成的剧情摘要将自动绑定章节并持久化存入本地，关掉软件也绝不丢失。

---

## 📸 界面预览 (Screenshots)

请在项目根目录创建 `docs` 文件夹，并放入以下截图：
* `screenshot_bookshelf.jpg` (书架首页)
* `screenshot_reader_day.jpg` (日间阅读界面)
* `screenshot_reader_night.jpg` (夜间阅读界面)
* `screenshot_ai_summary.jpg` (AI 总结界面)

---

## 🚀 安装与构建 (Installation & Build)

### 1. 本地开发与运行 (Windows / macOS / Linux)

确保你的电脑已安装 `Python 3.12+`。

# 1. 克隆仓库
git clone [https://github.com/YOUR_USERNAME/novel-reader-app.git](https://github.com/YOUR_USERNAME/novel-reader-app.git)
cd novel-reader-app

# 2. 安装核心依赖
pip install -r requirements.txt

# 3. 启动应用
python main.py

### 2. 编译 Android APK (云端/本地)

**方式一：使用 GitHub Actions 自动构建（极力推荐）**
本项目已配置自动化构建脚本。你只需：
1. `Fork` 本仓库到个人账号。
2. 在 Actions 页面启用并手动触发 `Build Android` 工作流。
3. 喝杯咖啡，构建成功后在 `Artifacts` 中下载生成的 APK 文件。

**方式二：本地手动编译（需要本地配置 Flutter SDK）**

flet build apk

## 📂 项目结构 (Project Structure)

```text
novel-reader-app/
├── main.py                # 核心源代码 (UI 层 + 解析引擎 + 状态调度)
├── requirements.txt       # Python 依赖清单
├── assets/                # 本地静态资源挂载目录
│   ├── fonts/             # 预置中文字体 (ttf)
│   └── backgrounds/       # 预置高斯纹理背景图 (牛皮纸等)
└── .github/workflows/     # CI/CD 自动化构建配置
```

## 🔐 隐私与安全声明

纯本地架构：你的所有书籍文件、阅读进度、排版偏好均保存在本地设备（AppData 或安卓沙盒），无任何云端数据收集。
API Key 安全：应用仅在触发“AI 总结”时，与你配置的 LLM 提供商进行接口直连通信。API Key 明文仅存放在本机配置文件中，请妥善保管你的配置文件，切勿将含有 Key 的文件或截图外传。

## 🤝 参与贡献 (Contributing)

发现 Bug？有更好的 UX 改进点？欢迎提交 Issue 或 Pull Request！
这是一款为热爱阅读的“极客”量身打造的产品，每一行代码的打磨都离不开社区的灵感碰撞。

## 📄 许可证 (License)

[MIT License](LICENSE)