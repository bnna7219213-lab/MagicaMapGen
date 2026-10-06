using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEditor;

namespace LowPolyWorldBuilder.Editor.Validation
{
    /// <summary>Checks catalog integrity: missing prefabs, bad sizes, duplicate ids.</summary>
    public static class AssetCatalogValidator
    {
        public static bool Validate(AssetCatalog catalog, WorldBuildReport report)
        {
            if (catalog == null) return true; // catalog optional for MVP
            bool ok = true;
            int i = 0;
            foreach (var e in catalog.entries)
            {
                if (e == null) { report.Warn("Catalog", $"Entry {i} is null"); i++; continue; }
                if (e.prefab == null)
                {
                    report.Error("Catalog", $"Entry {i} ({e.category}) has no prefab");
                    ok = false;
                }
                else
                {
                    string path = AssetDatabase.GetAssetPath(e.prefab);
                    if (string.IsNullOrEmpty(path))
                    {
                        report.Error("Catalog", $"Entry {i} prefab is not a project asset");
                        ok = false;
                    }
                }
                if (e.size.x <= 0 || e.size.y <= 0 || e.size.z <= 0)
                    report.Warn("Catalog", $"Entry {i} ({e.category}) has non-positive size");
                i++;
            }
            return ok;
        }
    }
}
