# Win7 兼容版打包说明（迭代专用）

以后改了 `miniagent/` 的代码，想给旧 Win7 出一份能跑的包，照下面做就行。

---

## 一、为什么要有这一套

原 `prepare.py` 打进便携包的是 **Python 3.8.10**。
Python 3.8 改了 DLL 安全加载方式（`SetDefaultDllDirectories` / `LOAD_LIBRARY_SEARCH_*`），
这套 API 在 Win7 上要靠补丁 **KB2533623** 才有。

裸 Win7 SP1（没打这个补丁）会直接崩：

```
ImportError: DLL load failed while importing _ssl: 参数错误
```

MiniAgent 启动时必然 `import ssl`（调大模型 API 走 HTTPS），所以整个程序起不来。

Python 3.7 用老式 `LoadLibrary`，不需要 KB2533623 → 换 3.7 就绕开了。

> 2026-11 实测：同一台裸 SP1 上，3.8 的 `ssl38_rc=1 / listtools38_rc=1`（崩），
> 3.7 的 `ssl37_rc=0 / sqlite37_rc=0 / listtools37_rc=0`（正常）。
> 另外微软已把 KB2533623 的 Win7 下载全部下线，所以「换 3.7」比「补补丁」现实得多。

---

## 二、以后的迭代流程（三步）

### 1. 改代码

正常改，正常测。`build.bat` / `prepare.py` 那套原流程**完全不动**，
Win10/11 用的 3.8 版继续照旧打。

### 2. 跑兼容检查（关键）

```bat
packaging\check_win7_compat.bat
```

四道检查，任何一道红了就先别打包：

| 检查 | 抓什么 |
|---|---|
| 语法层 | `ast.parse(feature_version=(3,7))`，命中 3.8+ 语法（`:=`、f-string `{x=}`、仅位置参数 `/`）直接报行号 |
| API 层 | 3.8/3.9 才有的运行时 API：`math.prod`、`functools.cached_property`、`str.removeprefix`、`typing.Literal/TypedDict/Protocol/Final`、`dict[str,...]` 泛型下标、`zoneinfo`、`asyncio.to_thread`、`graphlib` |
| 真编译 | 用内置 3.7 运行时 `compileall` 编译所有 .py，语法问题一网打尽 |
| 冒烟 | 用 3.7 跑 `run.py --list-tools`，看能否列出工具 |

只查源码不打包：`check_win7_compat.bat --src-only`

### 3. 打包

```bat
packaging\make_portable_win7.bat
```

产物：

- `packaging\build\MiniAgent-portable-win7\` — 文件夹，直接拷 U 盘
- `packaging\dist\MiniAgent-portable-win7.zip` — 压缩包（约 33 MB）

会自动附上启动脚本（`MiniAgent-CLI.bat` / `MiniAgent-Web.bat`，英文名避免 Win7 的 GBK 乱码）、
`Win7兼容说明.txt`、以及 `vc_redist.x64.exe`（旧机器缺 UCRT 时装一次）。

---

## 三、新增的文件

| 文件 | 作用 |
|---|---|
| `packaging/prepare_win7.py` | Win7 版打包脚本（3.7.9 运行时），原 `prepare.py` 一行没改 |
| `packaging/check_win7_compat.py` | 四道兼容性检查 |
| `packaging/make_portable_win7.bat` | 一键打包 + 检查 |
| `packaging/check_win7_compat.bat` | 只检查 |
| `packaging/build/runtime37/` | 缓存的 Python 3.7.9 embeddable（已下好，不用再联网） |
| `packaging/assets/vc_redist.x64.exe` | UCRT 安装包，打包时自动带上 |

运行时缓存没了也不要紧，`prepare_win7.py` 会自动从 python.org 下载，
失败自动退到华为云镜像。

---

## 四、什么情况下 3.7 会不够用

| 情况 | 后果 | 处理 |
|---|---|---|
| 用了 3.8+ 语法（海象运算符等） | `check` 第 1 道红 | 改写；或给 Win7 用户单独打个分支 |
| 用了 3.8+ 标准库新 API | `check` 第 2 道黄 | 换等价写法 |
| 引入第三方库 | 3.7 的 wheel 可能装不上 | 见下 |
| 需要 f-string `=` 调试、`typing.Protocol` 这类 | 拒绝 | 改写 |

### 加第三方库怎么办

3.7 embeddable 不带 pip。要装的话：

```bat
:: 一次性
curl -o get-pip.py https://bootstrap.pypa.io/pip/3.7/get-pip.py
packaging\build\runtime37\python.exe get-pip.py

:: 之后装库（注意版本要选支持 3.7 的）
packaging\build\runtime37\python.exe -m pip install "requests<2.32"
```

装完 `python\Lib\site-packages` 会跟着进便携包。

> 注意 `python37._pth` 默认没启用 `import site`，
> 如果装完库 import 不到，把 `build/runtime37/python37._pth` 里
> 最后一行 `#import site` 的 `#` 去掉再重打包。

---

## 五、在虚拟机里复测（可选）

`E:\AI\vm_stuff\Win7Test.vdi` 是那台实测用的 Win7 SP1 虚拟机，**不要删**。
它已经配成「每次登录自动跑光驱里的 `run_test.bat`」，复测只要三步：

1. 打新包，把新包放进 `E:\AI\vm_stuff\payload\MiniAgent-portable\`
2. 重建载荷 ISO：`cd E:\AI\vm_stuff && python make_payload_iso.py`
3. 挂 ISO 到 IDE-0-1，开虚拟机 → 自动跑 → 报告自动弹出

详见 `E:\AI\vm_stuff\README_复测.md`。
