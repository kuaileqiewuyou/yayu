# 测试与离线预览

在项目根目录安装依赖与 `pytest` 后执行：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\venv\Scripts\python.exe -m pytest tests -q
```

无需模型或语音服务的验证：

```powershell
.\venv\Scripts\python.exe scripts\smoke_sprite_pack.py --output-dir .sandbox\snapshots\sprite-pack
.\venv\Scripts\python.exe scripts\smoke_memory.py
.\venv\Scripts\python.exe scripts\smoke_streaming_cancel.py
```

这三个脚本使用隔离配置与模拟服务，验证立绘管理、记忆和流式取消。立绘脚本默认将截图放入临时目录并在结束时清理；上例通过 `--output-dir` 将截图保留在被忽略的 `.sandbox/`。另外两个脚本的输出位于被忽略的 `logs/`。

需要可见窗口的 CG 预览：

```powershell
.\venv\Scripts\python.exe scripts\manual_cg_preview_smoke.py
```

脚本创建 `manual-preview-smoke.png`，不需要启动 LLM 或 ComfyUI。关闭窗口后退出。真实模型、语音和图像服务需使用自己的配置单独验证。
