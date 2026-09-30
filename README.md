# 拾言 · Shiyan WeChat

把聊天中的话语拾起来，保存成自己的记录。

拾言是 Windows 上的本地微信聊天记录整理与导出工具。选择一个聊天，预览最近消息，再导出完整记录。

## 已有功能

- 选择本机微信账号，搜索聊天名称或微信号。
- 选择一个私聊或群聊，预览最近 50 条消息。
- 导出该聊天的完整历史为简化 TXT、JSON 或 SQLite。
- 按消息顺序逐条写入，显示导出进度，支持取消。
- TXT 保留时间、发送人和文字，非文字消息显示类型标记。

这里的“导入”是从微信本地数据库读取到窗口预览，尚不支持导入外部 JSON 文件。导出的是电脑本地已有的记录；手机上未迁移到电脑的消息不会自动补齐。

## 运行

需要 Windows 10/11、64 位 Python 3.10 或 3.12（含 Tkinter），并保持电脑版微信登录。

1. 下载本仓库 ZIP 并解压。
2. 双击 `setup.cmd`，创建项目专用环境并安装依赖。
3. 双击 `start.cmd` 打开拾言。
4. 选择账号与聊天，点击“导入并预览”，选择保存格式，再点击“导出选中聊天”。

也可以在项目目录中运行：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe export_gui.py
```

此版本为源码版，尚未提供独立 EXE 安装包。已在 Windows、Python 3.10、微信 4.1.13.65 上读取和导出验证；其他微信版本的兼容性由底层库决定。

## 导出格式

| 格式 | 内容 |
| --- | --- |
| TXT | 时间、发送人、文字内容；图片、语音、文件等显示为 `[图片]`、`[语音]` 等标记 |
| JSON | 单个会话信息及结构化消息数据 |
| SQLite | `chats` 与 `messages` 两张表，便于后续查询 |

TXT 暂不展开引用、链接、转账等非文字消息的详情。三个格式均不打包媒体原件。默认不覆盖已有文件；正常完成后才生成正式文件，取消或失败会清理临时文件。

## 本地数据

聊天读取和导出在本机完成。本应用没有云端上传功能。首次安装需要联网下载 Python 依赖。底层库会在系统临时目录 `wechatauto_db` 下建立数据库缓存和密钥缓存，请按个人隐私数据管理。

只读取和导出你本人拥有或获得授权访问的账号记录。分享导出文件前，请自行检查其中的个人信息。

## 开发与验证

```powershell
py -3 -m unittest discover -s tests -v
```

测试使用人工构造的数据库，检查跨分片顺序、中文和多行文字、三种格式、取消清理及已有文件保护，不使用真实聊天记录。

`export_core.py` 对固定版本底层库的内部数据库接口做了适配，升级依赖前需要重新验证。后续计划包括日期筛选、媒体文件整理和可浏览的 HTML 导出。

## 许可与致谢

拾言的界面与导出适配代码采用 [MIT License](LICENSE)，版权归 RoketrP。

微信数据读取能力依赖 [fanyuantaier/wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)，当前固定为 `1.2.4.1`，该依赖采用 Apache-2.0。上游许可副本见 [licenses/wechatauto-replica-LICENSE](licenses/wechatauto-replica-LICENSE)，详细说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目是独立的桌面界面与导出工具，与微信及腾讯没有官方关联。
