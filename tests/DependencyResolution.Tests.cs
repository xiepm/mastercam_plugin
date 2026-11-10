using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using MC2027Suite;

internal static class DependencyResolutionTests
{
    static int Main(string[] args)
    {
        string root=Directory.GetParent(Path.GetDirectoryName(typeof(DependencyResolutionTests).Assembly.Location)).FullName;
        string scenario=args[0];
        string Porsche()=>Path.Combine(root,"PorscheAdvanced2027","PorscheAdvanced2027.dll");
        void Assert(bool value,string message){if(!value)throw new Exception(message);}
        void Fails(Action action,string text){try{action();}catch(Exception e){Assert(e.ToString().Contains(text),e.ToString());return;}throw new Exception("Expected failure: "+text);}
        try
        {
            switch(scenario)
            {
                case "cold-resolve":
                    var a=AssemblyLoadContext.Default.LoadFromAssemblyPath(Porsche());
                    Fails(()=>a.GetTypes(),"AdvancedDrill2027");
                    PluginDependencies.Register();PluginDependencies.Register();
                    Assert(a.GetTypes().Length==2,"Cold type enumeration failed");
                    PluginDependencies.EnsureForCommand("PorscheAdvanced2027");
                    Assert(AssemblyLoadContext.Default.Assemblies.Count(x=>x.GetName().Name=="AdvancedDrill2027")==1,"Duplicate dependency");
                    break;
                case "forward-transitive":
                    PluginDependencies.EnsureForCommand("MPRebuild2027");
                    var mp=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(root,"MPRebuild2027","MPRebuild2027.dll"));
                    Assert(mp.GetTypes().Length==1,"Transitive types failed");
                    break;
                case "missing-file":
                    File.Move(Path.Combine(root,"AdvancedDrill2027","AdvancedDrill2027.dll"),Path.Combine(root,"AdvancedDrill2027","missing.dll"));
                    Fails(()=>PluginDependencies.EnsureForCommand("PorscheAdvanced2027"),"工艺助手缺少依赖 AdvancedDrill2027");
                    break;
                case "wrong-file-version":
                    File.Copy(Path.Combine(root,"wrong","AdvancedDrill2027.dll"),Path.Combine(root,"AdvancedDrill2027","AdvancedDrill2027.dll"),true);
                    Fails(()=>PluginDependencies.EnsureForCommand("PorscheAdvanced2027"),"插件文件版本不匹配");
                    break;
                case "loaded-other-location":
                    AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(root,"other","AdvancedDrill2027.dll"));
                    Fails(()=>PluginDependencies.EnsureForCommand("PorscheAdvanced2027"),"已加载其他版本或位置");
                    break;
                case "requested-other-version":
                    PluginDependencies.Register();
                    Fails(()=>Assembly.Load("AdvancedDrill2027, Version=9.0.0.0, Culture=neutral, PublicKeyToken=null"),"插件依赖版本不匹配");
                    break;
                case "unknown-not-intercepted":
                    PluginDependencies.Register();
                    Fails(()=>Assembly.Load("UnknownSuiteTest, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"),"UnknownSuiteTest");
                    Assert(!AssemblyLoadContext.Default.Assemblies.Any(x=>x.GetName().Name=="AdvancedDrill2027"),"Unrelated request loaded dependencies");
                    break;
                case "unrelated-command":
                    PluginDependencies.EnsureForCommand("LittleBee2027");
                    Assert(!AssemblyLoadContext.Default.Assemblies.Any(x=>x.GetName().Name=="AdvancedDrill2027"),"Unrelated command loaded dependencies");
                    break;
                default:throw new Exception("Unknown scenario");
            }
            Console.WriteLine("PASS "+scenario);return 0;
        }
        catch(Exception e){Console.Error.WriteLine(e);return 1;}
    }
}
