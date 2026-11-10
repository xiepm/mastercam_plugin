using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;

namespace MC2027Suite;

// Only suite-owned cross-module dependencies. Never probe arbitrary folders or SDK DLLs.
internal static class PluginDependencies
{
    static readonly object Gate = new object();
    static bool registered;
    static readonly Dictionary<string, string> Versions = new(StringComparer.OrdinalIgnoreCase)
    {
        ["OperationTools2027"] = "1.0.3.0",
        ["AdvancedDrill2027"] = "0.1.2.0",
        ["PorscheAdvanced2027"] = "1.0.0.0"
    };

    internal static void Register()
    {
        lock (Gate)
        {
            if (registered) return;
            AssemblyLoadContext.Default.Resolving += Resolve;
            registered = true;
        }
    }

    internal static void EnsureForCommand(string application)
    {
        Register();
        if (application == "PorscheAdvanced2027" || application == "MPRebuild2027")
        {
            // FT dispatch enumerates types before calling the target's Init/Run.
            // Resolve before that boundary so a missing installation gives our normal UI error.
            Load("OperationTools2027");
            Load("AdvancedDrill2027");
            if (application == "MPRebuild2027") Load("PorscheAdvanced2027");
        }
    }

    static Assembly Resolve(AssemblyLoadContext context, AssemblyName requested)
    {
        if (!Versions.ContainsKey(requested.Name ?? "")) return null;
        string expected = FullName(requested.Name);
        if (!string.Equals(requested.FullName, expected, StringComparison.OrdinalIgnoreCase))
            throw new FileLoadException("插件依赖版本不匹配：" + requested.FullName + "。请更新完整插件套件并重启 Mastercam。");
        return Load(requested.Name);
    }

    static string FullName(string name) => name + ", Version=" + Versions[name] + ", Culture=neutral, PublicKeyToken=null";

    static Assembly Load(string name)
    {
        lock (Gate)
        {
            string root = Directory.GetParent(Path.GetDirectoryName(typeof(PluginDependencies).Assembly.Location)).FullName;
            string path = Path.Combine(root, name, name + ".dll");
            if (!File.Exists(path))
                throw new FileNotFoundException("工艺助手缺少依赖 " + name + "。请重新运行完整安装包的 Install.cmd。\n预期位置：" + path, path);
            string expected = FullName(name);
            var disk = AssemblyName.GetAssemblyName(path);
            if (!string.Equals(disk.FullName, expected, StringComparison.OrdinalIgnoreCase))
                throw new FileLoadException("插件文件版本不匹配：" + path + "\n需要 " + expected + "\n实际 " + disk.FullName + "\n请更新完整插件套件并重启 Mastercam。", path);
            var loaded = AssemblyLoadContext.Default.Assemblies.FirstOrDefault(a => string.Equals(a.GetName().Name, name, StringComparison.OrdinalIgnoreCase));
            if (loaded != null)
            {
                if (!string.Equals(loaded.FullName, expected, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(Path.GetFullPath(loaded.Location), Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase))
                    throw new FileLoadException("Mastercam 已加载其他版本或位置的 " + name + "。请关闭并重新启动 Mastercam 后再试。", path);
                return loaded;
            }
            return AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(path));
        }
    }
}
