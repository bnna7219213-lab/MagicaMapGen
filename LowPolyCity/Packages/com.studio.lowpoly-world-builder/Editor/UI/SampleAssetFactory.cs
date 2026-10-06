using LowPolyWorldBuilder.Config;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.UI
{
    /// <summary>
    /// Creates the default profile + zones + palette assets so a fresh project
    /// reaches the 4x4 closed loop without any manual asset setup.
    /// </summary>
    public static class SampleAssetFactory
    {
        public const string ConfigFolder = "Assets/LowPolyWorldBuilder/Config";

        [MenuItem("Tools/Low Poly World Builder/Create Default Profile")]
        public static void CreateDefaultProfileMenu() => CreateDefaultProfileWithZones();

        public static WorldBuildProfile CreateDefaultProfileWithZones()
        {
            EnsureFolder("Assets/LowPolyWorldBuilder");
            EnsureFolder(ConfigFolder);

            var palette = CreateAsset<StylePalette>(ConfigFolder + "/DefaultPalette.asset");
            var residential = CreateAsset<ZoneProfile>(ConfigFolder + "/Zone_Residential.asset");
            residential.usage = ZoneUsage.Residential;
            residential.spawnWeight = 3f;
            residential.heightMultiplier = new Vector2(0.5f, 0.9f);
            residential.greenery = 0.5f;

            var commercial = CreateAsset<ZoneProfile>(ConfigFolder + "/Zone_Commercial.asset");
            commercial.usage = ZoneUsage.Commercial;
            commercial.spawnWeight = 2f;
            commercial.heightMultiplier = new Vector2(0.8f, 1.4f);
            commercial.greenery = 0.2f;

            var park = CreateAsset<ZoneProfile>(ConfigFolder + "/Zone_Park.asset");
            park.usage = ZoneUsage.Park;
            park.spawnWeight = 1f;
            park.heightMultiplier = new Vector2(0.15f, 0.25f);
            park.greenery = 1f;

            var catalog = CreateAsset<AssetCatalog>(ConfigFolder + "/DefaultCatalog.asset");

            var profile = CreateAsset<WorldBuildProfile>(ConfigFolder + "/CartoonCity_4x4.asset");
            profile.worldName = "CartoonCity_4x4";
            profile.seed = 12345;
            profile.blockCount = new Vector2Int(4, 4);
            profile.blockSize = 80f;
            profile.roadWidth = 12f;
            profile.sidewalkWidth = 3f;
            profile.zones = new[] { residential, commercial, park };
            profile.palette = palette;
            profile.catalog = catalog;
            profile.outputFolder = "Assets/LowPolyWorldOutput";

            EditorUtility.SetDirty(profile);
            AssetDatabase.SaveAssets();
            Selection.activeObject = profile;
            Debug.Log("[LPW] Default profile created at " + ConfigFolder + "/CartoonCity_4x4.asset");
            return profile;
        }

        static T CreateAsset<T>(string path) where T : ScriptableObject
        {
            var existing = AssetDatabase.LoadAssetAtPath<T>(path);
            if (existing != null) return existing;
            var a = ScriptableObject.CreateInstance<T>();
            AssetDatabase.CreateAsset(a, path);
            return a;
        }

        static void EnsureFolder(string folder)
        {
            if (AssetDatabase.IsValidFolder(folder)) return;
            var parts = folder.Split('/');
            string cur = parts[0];
            for (int i = 1; i < parts.Length; i++)
            {
                string next = cur + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(cur, parts[i]);
                cur = next;
            }
        }
    }
}
