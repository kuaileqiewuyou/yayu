# 芽语 · 开发协作说明

## 开发环境

在仓库根目录工作，使用 Python 3.11 或更新版本和项目虚拟环境。以下命令中的 `python` 指已激活虚拟环境的解释器；也可以直接使用 Windows 的 `./venv/Scripts/python.exe` 或 Linux 的 `./venv/bin/python`。

```text
python -m venv venv
```

创建后先激活虚拟环境：

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

```bash
# Linux / Bash
source venv/bin/activate
```

然后安装基础依赖与测试依赖：

```text
python -m pip install -r requirements.txt
python -m pip install pytest pytest-qt
```

## 测试命令

外部 `PYTHONPATH`、`PYTHONHOME` 或另一套虚拟环境可能影响导入。使用项目解释器的 `-E` 参数忽略 Python 环境变量，并清除继承的 `VIRTUAL_ENV`；测试子进程也会继承当前环境，因此建议同时清除前两项。

```powershell
# Windows PowerShell；只修改当前进程的环境
Remove-Item Env:PYTHONPATH,Env:PYTHONHOME,Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$env:QT_QPA_PLATFORM = "offscreen"
python -E -m pytest -q
```

```bash
# Linux / Bash
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV QT_QPA_PLATFORM=offscreen python -E -m pytest -q
```

迭代时可先运行启动、聊天界面与模型流水线的回归集：

```text
python -E -m pytest -q tests/test_chat_app_bootstrap.py tests/test_chat_ui_status.py tests/test_llm_setup.py tests/test_llm_worker_tool_loop.py tests/test_ui_smoke.py
```

Qt 测试需要真实 PySide6 和 QtMultimedia；`QT_QPA_PLATFORM=offscreen` 可在没有显示器时运行。终端测试还会执行本地 `printf`、`sleep`、`sh`、`bash`、`python`，部分 PTY 测试需要 `winpty`。Windows 可将 Git for Windows 的 `usr/bin` 临时加入当前进程的 `PATH`，并将项目虚拟环境的 `Scripts` 目录放在它前面。缺少这些依赖时，应明确记录环境限制和具体失败，不能声称全量测试通过。

## 离线与数据隔离

测试通过临时配置、临时会话与假模型适配器验证功能，不需要真实 API Key。HTTP 适配器使用模拟传输，流式取消测试使用自己启动的本机回环服务；不要为了测试填写真实模型服务凭据。

验证发布内容时，使用只含公开文件的干净检出目录运行测试。不要把日常使用的 `api.local.yaml`、角色配置、聊天历史、记忆数据库或个人资源复制到测试目录。离线截图与子进程烟测可能在 `logs/` 产生图片，这些输出也不属于提交内容。更多说明见 [测试与离线预览](docs/testing.md)。

## 提交前检查

- 迭代期间先跑相关回归；声明版本测试通过前，运行完整 `python -E -m pytest -q`。
- 如果失败只在成组或全量测试出现，先检查共享状态、`sys.modules` 替身和导入顺序，再判断是否为产品代码问题。
- 检查准备提交的文件清单和差异，排除 API Key、本机服务地址、个人角色与素材、聊天记录、记忆、日志和临时截图。Git 忽略规则不会自动移除已经被跟踪的文件。
- 用户指南与测试应描述公开代码的行为，不依赖个人电脑路径、内部开发状态文档或一次性的人工验收记录。
