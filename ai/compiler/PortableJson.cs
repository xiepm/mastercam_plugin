// Compatibility adapter for the original P08 smoke fixture on NET-Script 2027.
public sealed class AicncPortableJson {
 public T Deserialize<T>(string text) {
  using(var doc=System.Text.Json.JsonDocument.Parse(text))return (T)Convert(doc.RootElement);
 }
 public string Serialize(object value) { return System.Text.Json.JsonSerializer.Serialize(value); }
 private static object Convert(System.Text.Json.JsonElement e) {
  switch(e.ValueKind) {
   case System.Text.Json.JsonValueKind.Object:
    var d=new System.Collections.Generic.Dictionary<string,object>();
    foreach(var p in e.EnumerateObject())d[p.Name]=Convert(p.Value);return d;
   case System.Text.Json.JsonValueKind.Array:
    var a=new System.Collections.Generic.List<object>();foreach(var v in e.EnumerateArray())a.Add(Convert(v));return a.ToArray();
   case System.Text.Json.JsonValueKind.String:return e.GetString();
   case System.Text.Json.JsonValueKind.Number:return e.GetDouble();
   case System.Text.Json.JsonValueKind.True:return true;
   case System.Text.Json.JsonValueKind.False:return false;
   default:return null;
  }
 }
}
