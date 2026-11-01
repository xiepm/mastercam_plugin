using System;
using System.IO;
using System.Reflection;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Threading;
class Mc2027Compile {
 static int Main(string[] args) {
  if(args.Length<2) { Console.Error.WriteLine("Usage: script.csx mastercam-root"); return 2; }
  string root=Path.GetFullPath(args[1]);
  string dir=Path.Combine(root,"chooks","MCNetScripting");
  AppDomain.CurrentDomain.AssemblyResolve += (sender,e) => {
   string path=Path.Combine(dir,new AssemblyName(e.Name).Name+".dll");
   return File.Exists(path)?Assembly.LoadFrom(path):null;
  };
  var sa=Assembly.LoadFrom(Path.Combine(dir,"Microsoft.CodeAnalysis.Scripting.dll"));
  var ca=Assembly.LoadFrom(Path.Combine(dir,"Microsoft.CodeAnalysis.CSharp.Scripting.dll"));
  var ot=sa.GetType("Microsoft.CodeAnalysis.Scripting.ScriptOptions",true);
  object options=ot.GetProperty("Default").GetValue(null,null);
  var refs=new List<string>();
  refs.Add(Path.Combine(root,"NETHook3_0.dll"));
  if(args.Length>1) refs.AddRange(((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")).Split(Path.PathSeparator));
  var add=ot.GetMethods().Single(m=>m.Name=="AddReferences"&&m.GetParameters().Length==1&&m.GetParameters()[0].ParameterType==typeof(IEnumerable<string>));
  options=add.Invoke(options,new object[]{refs});
  var ct=ca.GetType("Microsoft.CodeAnalysis.CSharp.Scripting.CSharpScript",true);
  var create=ct.GetMethods().Single(m=>m.Name=="Create"&&m.IsGenericMethodDefinition&&m.GetParameters()[0].ParameterType==typeof(string));
  object script=create.MakeGenericMethod(typeof(object)).Invoke(null,new object[]{File.ReadAllText(args[0]),options,null,null});
  var compile=script.GetType().GetMethod("Compile",new[]{typeof(CancellationToken)});
  var diagnostics=(IEnumerable)compile.Invoke(script,new object[]{default(CancellationToken)});
  int errors=0;
  foreach(var diagnostic in diagnostics){Console.WriteLine(diagnostic);if(diagnostic.GetType().GetProperty("Severity").GetValue(diagnostic,null).ToString()=="Error")errors++;}
  Console.WriteLine("ERROR_COUNT="+errors);
  return errors==0?0:1;
 }
}
