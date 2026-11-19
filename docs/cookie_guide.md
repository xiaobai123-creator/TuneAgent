# 网易云登录凭证获取指南

TuneAgent 使用网易云网页 Cookie 中的 `MUSIC_U` 验证当前用户身份。请只使用
本人拥有并有权使用的账号，不要提交、分享或公开 Cookie。

## 方式一：Cookie-Editor 插件（推荐）

这是最直观的方式，不需要浏览器内核或额外 Python 包。

1. 在 Chrome 或 Edge 中安装 `Cookie-Editor` 插件。
2. 打开并登录 `https://music.163.com/`。
3. 点击浏览器工具栏中的 `Cookie-Editor` 图标。
4. 确认当前域名是 `music.163.com`。
5. 在列表中找到名为 `MUSIC_U` 的 Cookie。
6. 只复制 `MUSIC_U` 的 `Value`。
7. 在 TuneAgent CLI 中输入 `/login`，粘贴 Value 后按 Enter。

Cookie 输入过程不会显示字符。验证成功后，CLI 会自动写入
`.netease_cookie` 文件。

## 方式二：本地轻量脚本（备选）

脚本直接读取本机 Chrome 或 Edge 的 Cookie 数据库，不下载浏览器内核。

```bash
python -m pip install browser-cookie3
python scripts/get_cookie_local.py
```

运行前请先登录网易云并完全关闭 Chrome 或 Edge。脚本会在当前目录生成
`netease_cookie.txt`。复制该文件内容，在 TuneAgent CLI 中输入 `/login`
后粘贴即可。

新版浏览器可能因 Cookie 数据库锁定、macOS Keychain 权限或 Chrome 加密机制
导致读取失败。遇到错误时，优先使用 Cookie-Editor 方案。

## 方式三：浏览器 F12 手动获取

1. 在 Chrome 或 Edge 中登录 `https://music.163.com/`。
2. 按 `F12` 打开开发者工具。macOS 也可使用 `Cmd + Option + I`。
3. 打开 `Application` 或 `Storage`。
4. 进入 `Cookies`，选择 `https://music.163.com`。
5. 找到名为 `MUSIC_U` 的 Cookie。
6. 复制它的 `Value`。
7. 返回 TuneAgent CLI，输入 `/login` 并粘贴。

## 在 CLI 中使用

启动交互式 CLI：

```bash
python scripts/interactive_cli.py
```

在 `TuneAgent >` 提示符后输入：

```text
/login
```

粘贴 `MUSIC_U` 的 Value 或完整 `MUSIC_U=...` 内容后按 Enter。CLI 会先验证
登录状态，只有验证成功才覆盖 `.netease_cookie`。

如果 `.env` 中配置了 `NETEASE_COOKIE` 或 `NETEASE_MUSIC_U`，这些环境变量
会优先于 `.netease_cookie`。重新登录后如果仍读取旧凭证，请删除或更新环境
变量配置。
