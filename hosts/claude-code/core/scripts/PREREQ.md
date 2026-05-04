# CCPal 安装前必读

给真不会用命令行的人看。**已经懂 Claude Code 的人可跳过本文,直接把 install.html 给 Claude Code,说一句"装一下"即可。**

---

## 一、你需要什么(三件)

| 项 | 怎么验证 | 缺了怎么办 |
|---|---|---|
| **macOS** | 看左上角苹果菜单 → 关于本机 | 不支持 Linux/Windows,本工具到此为止 |
| **Claude Code** | 终端跑 `claude` 能进 | 去 https://claude.com/claude-code 装一遍 |
| **git** | 终端跑 `git --version` 能出版本号 | 跑 `xcode-select --install`,弹窗里点 Install,等 5-10 分钟 |

> Python 3、bash、rsync、curl 都是 macOS 自带的,无需额外装。

---

## 二、怎么开装(2 种方式,任选其一)

### 方式 A · 在 Claude Code 里装(最简单,推荐)

1. 打开 Claude Code 终端(在你想装 CCPal 的 mac 上)
2. 把 install.html 拖到 Claude Code 输入框,**或者**输入:
   ```
   读 /Users/你的用户名/Downloads/install.html 按里面指令装一下
   ```
3. Claude 先做环境预检,告诉你能不能装
4. 看到 **"环境就绪,回复「是」开始"** → 输入 `是` 或 `确认`
5. 等 1-2 分钟,浏览器自动弹出 http://127.0.0.1:8765

### 方式 B · 命令行手装(给极客)

```bash
cd /path/to/CCPal-source
bash install.sh
bash scripts/start-history.sh
```

---

## 三、安装期间会出现的系统弹窗(都点 Allow)

| 弹窗 | 何时出现 | 点什么 |
|---|---|---|
| "安装命令行开发者工具" | git 未装时首次跑 git | Install,等下载完 |
| "允许 com.claude.* 在后台运行" | macOS Sonoma+ 加载 launchd 任务时 | 系统设置 → 通用 → 登录项 → 允许 |
| "Terminal 想控制 Chrome/Safari" | 首次自动打开浏览器 | 允许 |

这些是 macOS 安全机制,**任何安装程序都绕不过**。

---

## 四、装好之后

打开 http://127.0.0.1:8765 — 五个页面:

- **主页**:历史对话浏览/搜索/附件
- **统计**:Token 消耗趋势
- **健康**:工作节律 + 提醒
- **套餐**:5h session / 7d weekly 滚动
- **数据安全**:数据位置说明

---

## 五、隐私 / 占用 / 卸载

- **隐私**:所有数据 100% 本地,零外部传输
- **占用**:约 1-3 GB(看你历史对话量),备份目录 `~/CCPal-Backup` 占多一份
- **卸载**:运行 `bash ~/.claude/scripts/ccpal-doctor.sh` 看清单,然后参考 INSTALL.md 反向删除。**对话原文 ~/.claude/projects/ 不会被卸载脚本动**。

---

## 六、出问题怎么办

任何时候在 Claude Code 里说:

```
跑 ~/.claude/scripts/ccpal-doctor.sh
```

会自动检查 23 项,缺啥补啥。
