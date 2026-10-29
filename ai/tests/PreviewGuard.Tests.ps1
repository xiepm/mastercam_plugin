$ErrorActionPreference='Stop'
# Compiles the production guard itself; no Mastercam or mocked SDK is involved.
$guard=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../bridge/PreviewGuard.cs') -Raw
$checks=@'
public static class PreviewGuardChecks
{
    static void Need(bool b,string message) { if(!b)throw new System.Exception(message); }
    public static int Run() {
        int checks=0,builds=0;
        var g=new MastercamPluginAI.PreviewGuard("approved-A");
        try{g.Rebuild(()=>{builds++;return "changed-B";},x=>x);throw new System.Exception("drift accepted");}
        catch(System.InvalidOperationException){}
        Need(!g.IsValid&&g.Approved=="approved-A","drift must invalidate without changing approval");checks++;
        try{g.Rebuild(()=>{builds++;return "changed-B";},x=>x);throw new System.Exception("second attempt accepted");}
        catch(System.InvalidOperationException){}
        Need(builds==1,"new request must not rebuild/apply invalid approval");checks++;
        var f=new MastercamPluginAI.PreviewGuard("A");
        try{f.Rebuild<string>(()=>throw new System.Exception("build failed"),x=>x);}catch(System.Exception){}
        Need(!f.IsValid&&f.Approved=="A","failed build must invalidate");checks++;
        var s=new MastercamPluginAI.PreviewGuard("A");
        try{s.Rebuild(()=>"A",x=>throw new System.Exception("serialization failed"));}catch(System.Exception){}
        Need(!s.IsValid,"failed comparison must invalidate");checks++;
        var good=new MastercamPluginAI.PreviewGuard("A");
        Need(good.Rebuild(()=>"A",x=>x)=="A"&&good.IsValid,"matching preview should proceed");checks++;
        return checks;
    }
}
'@
Add-Type -TypeDefinition ($guard+"`n"+$checks)
$count=[MastercamPluginAI.PreviewGuardChecks]::Run()
Write-Output "PreviewGuard: $count regression checks PASS"
