using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
namespace MastercamPluginAI;

// Native library IO normalizes unit view matrices. Only those dimensionless
// components admit 1e-12 absolute roundoff. Transient face tags may be reallocated;
// persistent PIDs, face topology/type/normal/color, timestamps and all other fields stay exact.
internal static class LibraryState
{
    internal static string Capture(){using var selection=new PorscheAdvanced2027.GeometrySelection();return WorkshopBindings.Encode(new{
        database=PorscheBindings.DatabaseFacts(),
        solid_faces=PorscheAdvanced2027.GeometrySelection.All().OfType<Mastercam.Database.SolidGeometry>().Where(g=>Mastercam.Support.SearchManager.GetFaceTagsAndPidMapFromBodyEntity(g.GetEntityID())?.Count>0).OrderBy(g=>g.GetEntityID()).Select(g=>new{id=g.GetEntityID(),faces=GeometryAdapter.HostGeometry.Faces(g.GetEntityID()).Select(f=>new{f.Pid,f.Type,f.Normal,f.Color,f.ColorSource,edge_count=Mastercam.Support.SearchManager.GetEdgeTagsFromFace(f.Tag)?.Length})}),
        groups=WorkshopBindings.Groups().OrderBy(g=>g.ID).Select(g=>new{g.ID,g.Name,parent=g.GetParentGroup()?.ID})
    });}
    internal static void RequireEqual(string before,string after,string directory,string phase)
    {
        using var a=JsonDocument.Parse(before);using var b=JsonDocument.Parse(after);
        var differences=new List<object>();bool ok=true;
        void Compare(JsonElement x,JsonElement y,string path){
            if(x.GetRawText()==y.GetRawText())return;
            if(x.ValueKind==JsonValueKind.Object&&y.ValueKind==JsonValueKind.Object){
                var xp=x.EnumerateObject().ToDictionary(p=>p.Name,p=>p.Value);var yp=y.EnumerateObject().ToDictionary(p=>p.Name,p=>p.Value);
                if(xp.Keys.Order().SequenceEqual(yp.Keys.Order())){foreach(var p in xp)Compare(p.Value,yp[p.Key],path+"."+p.Key);return;}
            }
            if(x.ValueKind==JsonValueKind.Array&&y.ValueKind==JsonValueKind.Array&&x.GetArrayLength()==y.GetArrayLength()){for(int i=0;i<x.GetArrayLength();i++)Compare(x[i],y[i],path+"["+i+"]");return;}
            bool roundoff=path.StartsWith("$.database.planes[")&&System.Text.RegularExpressions.Regex.IsMatch(path,@"\.ViewMatrix\.Row[123]\.[xyz]$")&&x.ValueKind==JsonValueKind.Number&&y.ValueKind==JsonValueKind.Number&&double.IsFinite(x.GetDouble())&&double.IsFinite(y.GetDouble())&&Math.Abs(x.GetDouble()-y.GetDouble())<=1e-12;
            bool retag=System.Text.RegularExpressions.Regex.IsMatch(path,@"^\$\.database\.geometry\[\d+\]\.faces\[\d+\]\.Value$")&&x.ValueKind==JsonValueKind.Number&&y.ValueKind==JsonValueKind.Number;
            differences.Add(new{path,before=x.Clone(),after=y.Clone(),accepted_matrix_roundoff=roundoff,transient_face_tag=retag});if(!roundoff&&!retag)ok=false;
        }
        Compare(a.RootElement,b.RootElement,"$");Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory,phase+"-comparison.json"),WorkshopBindings.Encode(new{ok,matrix_absolute_tolerance=1e-12,differences}));
        File.WriteAllText(Path.Combine(directory,phase+"-before.json"),before);File.WriteAllText(Path.Combine(directory,phase+"-after.json"),after);
        if(!ok)throw new InvalidOperationException("Native library state mismatch; see "+phase+"-comparison.json");
    }
}
