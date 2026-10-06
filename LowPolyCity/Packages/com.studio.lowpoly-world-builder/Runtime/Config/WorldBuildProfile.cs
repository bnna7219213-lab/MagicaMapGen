using UnityEngine;

namespace LowPolyWorldBuilder.Config
{
    public enum WorldTheme
    {
        City,
        Railway,
        Metro,
        Harbor,
        Airport
    }

    /// <summary>
    /// Root generation configuration. Seed + content + generator version fully
    /// determine the generated result (plan section 5.3).
    /// </summary>
    [CreateAssetMenu(menuName = "LowPolyWorld/World Build Profile", fileName = "WorldBuildProfile")]
    public sealed class WorldBuildProfile : ScriptableObject
    {
        public int schemaVersion = 1;
        public string worldName = "CartoonCity";
        public int seed = 12345;
        public WorldTheme theme = WorldTheme.City;

        [Header("Grid")]
        [Tooltip("Number of city blocks in X/Z. MVP target: 4x4.")]
        public Vector2Int blockCount = new Vector2Int(4, 4);
        [Tooltip("Edge length of one block in meters.")]
        public float blockSize = 80f;
        public float roadWidth = 12f;
        public float sidewalkWidth = 3f;

        [Header("Density & Buildings")]
        [Range(0f, 1f)] public float lotFillRatio = 0.85f;
        public float minBuildingHeight = 8f;
        public float maxBuildingHeight = 40f;
        public Vector2 lotSizeRange = new Vector2(16f, 30f);

        [Header("Style & Assets")]
        public ZoneProfile[] zones;
        public StylePalette palette;
        public AssetCatalog catalog;

        [Header("Output")]
        [Tooltip("Folder (relative to project Assets) where scene/prefab/report are saved.")]
        public string outputFolder = "Assets/LowPolyWorldOutput";

        public float Pitch => blockSize + roadWidth;

        public Vector2Int GridNodeCount => new Vector2Int(blockCount.x + 1, blockCount.y + 1);

        public float WorldSizeX => blockCount.x * Pitch + roadWidth;
        public float WorldSizeZ => blockCount.y * Pitch + roadWidth;
    }
}
