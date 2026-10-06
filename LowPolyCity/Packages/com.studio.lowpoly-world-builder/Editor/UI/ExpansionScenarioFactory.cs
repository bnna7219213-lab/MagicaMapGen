using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.UI
{
    /// <summary>Creates version-controlled profiles for the transport theme and scale sweep.</summary>
    public static class ExpansionScenarioFactory
    {
        const string Root = "Assets/LowPolyWorldBuilder/Config/Expansion";

        public static List<WorldBuildProfile> CreateProfiles()
        {
            SampleAssetFactory.CreateDefaultProfileWithZones();
            EnsureFolder(Root);

            var result = new List<WorldBuildProfile>();
            var themes = new[] { WorldTheme.City, WorldTheme.Railway, WorldTheme.Metro, WorldTheme.Harbor, WorldTheme.Airport };
            foreach (var theme in themes)
            {
                var palette = GetPalette(theme);
                var zones = GetZones(theme);
                foreach (int size in new[] { 4, 16 })
                {
                    string scenario = theme + "_" + size + "x" + size;
                    string path = Root + "/" + scenario + ".asset";
                    var profile = AssetDatabase.LoadAssetAtPath<WorldBuildProfile>(path);
                    if (profile == null)
                    {
                        profile = ScriptableObject.CreateInstance<WorldBuildProfile>();
                        AssetDatabase.CreateAsset(profile, path);
                    }

                    profile.worldName = scenario;
                    profile.theme = theme;
                    profile.seed = 20261002 + (int)theme * 10000 + size;
                    profile.blockCount = new Vector2Int(size, size);
                    profile.blockSize = 80f;
                    profile.roadWidth = 12f;
                    profile.sidewalkWidth = 3f;
                    profile.lotFillRatio = 0.82f;
                    profile.minBuildingHeight = 8f;
                    profile.maxBuildingHeight = size == 16 ? 46f : 40f;
                    profile.lotSizeRange = new Vector2(16f, 30f);
                    profile.palette = palette;
                    profile.zones = zones;
                    profile.catalog = AssetDatabase.LoadAssetAtPath<AssetCatalog>("Assets/LowPolyWorldBuilder/Config/DefaultCatalog.asset");
                    profile.outputFolder = "Assets/LowPolyWorldOutput/Expansion/" + size + "x" + size + "/" + theme;
                    EditorUtility.SetDirty(profile);
                    result.Add(profile);
                }
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return result;
        }

        static StylePalette GetPalette(WorldTheme theme)
        {
            string path = Root + "/Palette_" + theme + ".asset";
            var palette = AssetDatabase.LoadAssetAtPath<StylePalette>(path);
            if (palette == null)
            {
                palette = ScriptableObject.CreateInstance<StylePalette>();
                AssetDatabase.CreateAsset(palette, path);
            }

            switch (theme)
            {
                case WorldTheme.Railway:
                    palette.ground = new Color(0.55f, 0.67f, 0.38f);
                    palette.road = new Color(0.26f, 0.27f, 0.29f);
                    palette.buildingWalls = new[] { new Color(0.86f, 0.55f, 0.36f), new Color(0.91f, 0.76f, 0.52f), new Color(0.64f, 0.72f, 0.7f) };
                    palette.buildingAccent = new Color(0.7f, 0.32f, 0.2f);
                    break;
                case WorldTheme.Metro:
                    palette.ground = new Color(0.47f, 0.62f, 0.61f);
                    palette.road = new Color(0.2f, 0.24f, 0.29f);
                    palette.buildingWalls = new[] { new Color(0.6f, 0.75f, 0.8f), new Color(0.85f, 0.79f, 0.64f), new Color(0.66f, 0.72f, 0.75f) };
                    palette.buildingGlass = new Color(0.55f, 0.82f, 0.9f);
                    palette.buildingAccent = new Color(0.85f, 0.4f, 0.45f);
                    break;
                case WorldTheme.Harbor:
                    palette.ground = new Color(0.57f, 0.68f, 0.48f);
                    palette.water = new Color(0.09f, 0.42f, 0.69f);
                    palette.buildingWalls = new[] { new Color(0.87f, 0.68f, 0.46f), new Color(0.79f, 0.49f, 0.33f), new Color(0.77f, 0.78f, 0.68f) };
                    palette.buildingAccent = new Color(0.75f, 0.28f, 0.2f);
                    break;
                case WorldTheme.Airport:
                    palette.ground = new Color(0.57f, 0.7f, 0.39f);
                    palette.road = new Color(0.24f, 0.26f, 0.29f);
                    palette.buildingWalls = new[] { new Color(0.78f, 0.84f, 0.84f), new Color(0.76f, 0.69f, 0.56f), new Color(0.64f, 0.76f, 0.84f) };
                    palette.buildingGlass = new Color(0.45f, 0.72f, 0.86f);
                    palette.buildingAccent = new Color(0.2f, 0.45f, 0.75f);
                    break;
                default:
                    palette.ground = new Color(0.48f, 0.68f, 0.38f);
                    break;
            }
            EditorUtility.SetDirty(palette);
            return palette;
        }

        static ZoneProfile[] GetZones(WorldTheme theme)
        {
            switch (theme)
            {
                case WorldTheme.Railway:
                    return new[]
                    {
                        CreateZone(theme, ZoneUsage.Rail, 2.6f, new Vector2(0.55f, 1.05f), 0.25f),
                        CreateZone(theme, ZoneUsage.Commercial, 2f, new Vector2(0.8f, 1.35f), 0.15f),
                        CreateZone(theme, ZoneUsage.Park, 0.8f, new Vector2(0.2f, 0.35f), 0.9f)
                    };
                case WorldTheme.Metro:
                    return new[]
                    {
                        CreateZone(theme, ZoneUsage.Metro, 2.7f, new Vector2(0.8f, 1.3f), 0.12f),
                        CreateZone(theme, ZoneUsage.Office, 1.9f, new Vector2(1f, 1.7f), 0.08f),
                        CreateZone(theme, ZoneUsage.Residential, 1.4f, new Vector2(0.55f, 0.95f), 0.35f),
                        CreateZone(theme, ZoneUsage.Park, 0.65f, new Vector2(0.2f, 0.4f), 0.9f)
                    };
                case WorldTheme.Harbor:
                    return new[]
                    {
                        CreateZone(theme, ZoneUsage.Harbor, 2.6f, new Vector2(0.6f, 1.2f), 0.08f),
                        CreateZone(theme, ZoneUsage.Industrial, 2.1f, new Vector2(0.55f, 1.15f), 0.12f),
                        CreateZone(theme, ZoneUsage.Commercial, 1.25f, new Vector2(0.85f, 1.35f), 0.18f),
                        CreateZone(theme, ZoneUsage.Park, 0.5f, new Vector2(0.2f, 0.4f), 0.8f)
                    };
                case WorldTheme.Airport:
                    return new[]
                    {
                        CreateZone(theme, ZoneUsage.Airport, 2.4f, new Vector2(0.9f, 1.5f), 0.08f),
                        CreateZone(theme, ZoneUsage.Office, 1.8f, new Vector2(0.9f, 1.45f), 0.14f),
                        CreateZone(theme, ZoneUsage.Commercial, 1.35f, new Vector2(0.8f, 1.3f), 0.18f),
                        CreateZone(theme, ZoneUsage.Park, 0.55f, new Vector2(0.2f, 0.4f), 0.82f)
                    };
                default:
                    return new[]
                    {
                        CreateZone(theme, ZoneUsage.Residential, 3f, new Vector2(0.5f, 0.9f), 0.5f),
                        CreateZone(theme, ZoneUsage.Commercial, 2f, new Vector2(0.8f, 1.4f), 0.2f),
                        CreateZone(theme, ZoneUsage.Park, 1f, new Vector2(0.15f, 0.25f), 1f)
                    };
            }
        }

        static ZoneProfile CreateZone(WorldTheme theme, ZoneUsage usage, float weight, Vector2 heights, float greenery)
        {
            string path = Root + "/Zone_" + theme + "_" + usage + ".asset";
            var zone = AssetDatabase.LoadAssetAtPath<ZoneProfile>(path);
            if (zone == null)
            {
                zone = ScriptableObject.CreateInstance<ZoneProfile>();
                AssetDatabase.CreateAsset(zone, path);
            }
            zone.usage = usage;
            zone.spawnWeight = weight;
            zone.heightMultiplier = heights;
            zone.greenery = greenery;
            EditorUtility.SetDirty(zone);
            return zone;
        }

        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            var parts = path.Split('/');
            string current = parts[0];
            for (int i = 1; i < parts.Length; i++)
            {
                string next = current + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, parts[i]);
                current = next;
            }
        }
    }
}
