using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyProduct("芽语 / Yayu")]
#if SETTINGS
[assembly: AssemblyTitle("芽语设置 / Yayu Settings")]
[assembly: AssemblyDescription("芽语 / Yayu 设置中心")]
#else
[assembly: AssemblyTitle("芽语 / Yayu")]
[assembly: AssemblyDescription("芽语 / Yayu AI 桌面伙伴")]
#endif

// Windows GUI host for a portable runtime or the source checkout's venv.
internal static class WindowsLauncher
{
    // These read-sharing handles match core/updates/locking.py. Holding the
    // parent EXE open is intentional: the updater must wait for both hosts.
    private static FileStream AcquireApplicationLock(string root)
    {
        string path = Path.Combine(root, ".yayu-app.lock");
        if (!File.Exists(path))
        {
            try { using (File.Open(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.ReadWrite)) { } }
            catch (IOException) { if (!File.Exists(path)) throw; }
        }
        try { return File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read); }
        catch (IOException)
        {
            throw new IOException("芽语正在更新，请等待更新完成后再启动。");
        }
    }

    private static string FullPath(string path)
    {
        return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    }

    private static string Field(Dictionary<string, object> value, string key)
    {
        object field;
        return value.TryGetValue(key, out field) && field is string ? (string)field : "";
    }

    private static bool IsUpdateRestart(string root)
    {
        string token = Environment.GetEnvironmentVariable("YAYU_UPDATE_TOKEN");
        if (string.IsNullOrEmpty(token)) return false;
        try
        {
            var pending = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(
                File.ReadAllText(Path.Combine(root, ".yayu-update-pending.json"), Encoding.UTF8));
            return Field(pending, "token") == token;
        }
        catch (IOException) { return false; }
        catch (ArgumentException) { return false; }
    }

    private static string RecoveryPath(string root, string path, string work)
    {
        string candidate = FullPath(path);
        string workspace = FullPath(Path.Combine(Directory.GetParent(FullPath(root)).FullName, ".yayu-updates"));
        string suffix = candidate.Substring(Math.Min(candidate.Length, workspace.Length));
        if (!candidate.StartsWith(workspace + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new IOException("更新恢复路径无效，请保留备份并重新下载程序。");
        string[] parts = suffix.TrimStart(Path.DirectorySeparatorChar).Split(Path.DirectorySeparatorChar);
        Guid identifier;
        if (parts.Length < 2 || parts[0].Length != 32 || !Guid.TryParseExact(parts[0], "N", out identifier))
            throw new IOException("更新恢复目录无效。");
        string job = Path.Combine(workspace, parts[0]);
        if (work != null && !job.Equals(work, StringComparison.OrdinalIgnoreCase))
            throw new IOException("更新恢复文件来自不同任务。");
        // Refuse directory links in the helper path; execute only the detached
        // runtime that this installation prepared beside its own directory.
        for (string current = candidate; current.Length >= workspace.Length; current = Path.GetDirectoryName(current))
        {
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("更新恢复路径包含链接，请从备份恢复程序。");
            if (current.Equals(workspace, StringComparison.OrdinalIgnoreCase)) break;
        }
        return candidate;
    }

    private static bool HandlePendingUpdate(string root)
    {
        string marker = Path.Combine(root, ".yayu-update-pending.json");
        if (!File.Exists(marker)) return false;
        if (new FileInfo(marker).Length > 32768) throw new IOException("更新标记无效。");
        var json = new JavaScriptSerializer();
        var pending = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(marker, Encoding.UTF8));
        string token = Field(pending, "token");
        if (string.IsNullOrEmpty(token) || !FullPath(Field(pending, "app_root")).Equals(FullPath(root), StringComparison.OrdinalIgnoreCase))
            throw new IOException("更新标记与当前安装目录不符，请保留备份并重新下载程序。");
        if (token == Environment.GetEnvironmentVariable("YAYU_UPDATE_TOKEN")) return false;

        string plan = RecoveryPath(root, Field(pending, "plan_path"), null);
        string work = Path.GetDirectoryName(plan);
        string python = RecoveryPath(root, Field(pending, "recovery_python"), work);
        string script = RecoveryPath(root, Field(pending, "recovery_script"), work);
        object worker;
        int pid;
        if (pending.TryGetValue("worker_pid", out worker) && int.TryParse(Convert.ToString(worker), out pid))
        {
            try
            {
                using (var running = Process.GetProcessById(pid))
                {
                    string image = FullPath(running.MainModule.FileName);
                    bool preparing = Field(pending, "state") == "prepared"
                        && image.Equals(FullPath(Path.Combine(root, "runtime", "python.exe")), StringComparison.OrdinalIgnoreCase);
                    if (!running.HasExited && (image.Equals(python, StringComparison.OrdinalIgnoreCase) || preparing))
                    {
                        MessageBox.Show("芽语正在更新，完成后会自动重新打开。请稍候。", "芽语 / Yayu",
                            MessageBoxButtons.OK, MessageBoxIcon.Information);
                        return true;
                    }
                }
            }
            catch (ArgumentException) { }
            catch (InvalidOperationException) { }
        }
        var start = new ProcessStartInfo(python, "-E -u \"" + script + "\" --recover \"" + plan + "\"");
        start.WorkingDirectory = work;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.EnvironmentVariables.Remove("PYTHONPATH");
        start.EnvironmentVariables.Remove("PYTHONHOME");
        start.EnvironmentVariables.Remove("VIRTUAL_ENV");
        // Do not wait here: the recovery helper must be able to replace this EXE.
        using (Process recovery = Process.Start(start)) { }
        return true;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        string root = AppDomain.CurrentDomain.BaseDirectory;
#if SETTINGS
        bool settings = true;
#else
        bool settings = Array.Exists(args, arg => arg == "--settings");
#endif
        string entry = settings ? "webui_qt.py" : "main.py";
        string portablePython = Path.Combine(root, "runtime", "python.exe");
        bool portable = File.Exists(portablePython);
        string python = portable ? portablePython : Path.Combine(root, "venv", "Scripts", "python.exe");
        string script = portable ? "portable_bootstrap.py" : entry;
        string logPath = null;
        FileStream instanceLock = null;
        try
        {
            // Recovery runs before runtime/entry checks, since an interrupted
            // replacement may temporarily have moved either file to backup.
            if (HandlePendingUpdate(root)) return 0;
            if (portable)
            {
                instanceLock = AcquireApplicationLock(root);
                if (File.Exists(Path.Combine(root, ".yayu-update-pending.json")))
                {
                    instanceLock.Dispose();
                    instanceLock = null;
                    if (HandlePendingUpdate(root)) return 0;
                    instanceLock = AcquireApplicationLock(root);
                }
            }
            if (!File.Exists(Path.Combine(root, entry)))
                throw new FileNotFoundException("找不到 " + entry + "。请将 exe 保留在项目根目录；桌面启动请创建快捷方式。");
            if (!File.Exists(Path.Combine(root, script)))
                throw new FileNotFoundException("便携包不完整：找不到 " + script + "。请重新完整解压下载包，勿单独移动 exe。");
            if (!File.Exists(python))
                throw new FileNotFoundException("找不到 runtime\\python.exe 或 venv\\Scripts\\python.exe。便携版请完整解压下载包；源码版请先创建 venv 并安装 requirements.txt 中的依赖。");

            string logs = Path.Combine(root, "logs");
            Directory.CreateDirectory(logs);
            logPath = Path.Combine(logs, (settings ? "settings-" : "chat-")
                + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "-"
                + Process.GetCurrentProcess().Id + ".log");
            using (var log = new StreamWriter(logPath, false, new UTF8Encoding(false)))
            using (var process = new Process())
            {
                log.AutoFlush = true;
                log.WriteLine("Started: " + DateTime.Now.ToString("O"));
                log.WriteLine("Entry: " + entry);
                string arguments = "-E -u \"" + script + "\"" + (portable && settings ? " --settings" : "");
                var start = new ProcessStartInfo(python, arguments);
                start.WorkingDirectory = root;
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.RedirectStandardOutput = true;
                start.RedirectStandardError = true;
                start.StandardOutputEncoding = Encoding.UTF8;
                start.StandardErrorEncoding = Encoding.UTF8;
                // Keep other hosts' Python environments out of this project.
                start.EnvironmentVariables.Remove("PYTHONPATH");
                start.EnvironmentVariables.Remove("PYTHONHOME");
                start.EnvironmentVariables.Remove("VIRTUAL_ENV");
                start.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                process.StartInfo = start;
                object logLock = new object();
                DataReceivedEventHandler capture = (sender, e) =>
                {
                    if (e.Data == null) return;
                    lock (logLock)
                    {
                        // A full disk must not crash an otherwise running UI.
                        try { log.WriteLine(e.Data); }
                        catch (IOException) { }
                    }
                };
                process.OutputDataReceived += capture;
                process.ErrorDataReceived += capture;
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                int exitCode = process.ExitCode;
                log.WriteLine("Exit code: " + exitCode);
                if (exitCode != 0 && !IsUpdateRestart(root))
                    MessageBox.Show("程序异常退出（代码 " + exitCode + "）。\n\n详细日志：\n" + logPath,
                        "芽语 / Yayu", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return exitCode;
            }
        }
        catch (Exception error)
        {
            // During probation the detached helper owns failure reporting and
            // rollback. A modal launcher error would keep this EXE locked.
            if (!IsUpdateRestart(root))
                MessageBox.Show("启动失败：\n" + error.Message
                    + (logPath == null ? "" : "\n\n日志位置：\n" + logPath),
                    "芽语 / Yayu", MessageBoxButtons.OK, MessageBoxIcon.Error);
            else if (logPath != null)
            {
                try { File.AppendAllText(logPath, "Startup failed: " + error.Message + Environment.NewLine, Encoding.UTF8); }
                catch (IOException) { }
            }
            return 1;
        }
        finally
        {
            if (instanceLock != null) instanceLock.Dispose();
        }
    }
}
