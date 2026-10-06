using UnityEngine;

namespace LowPolyWorldBuilder.Config
{
    public enum ZoneUsage
    {
        Residential,
        Commercial,
        Office,
        Industrial,
        Park,
        Rail,       // reserved: phase 5
        Harbor,     // reserved: phase 6
        Airport,
        Metro
    }

    /// <summary>
    /// One zone type: which building archetypes may appear, with what weight,
    /// and which palette color band is preferred.
    /// </summary>
    [CreateAssetMenu(menuName = "LowPolyWorld/Zone Profile", fileName = "ZoneProfile")]
    public sealed class ZoneProfile : ScriptableObject
    {
        public ZoneUsage usage = ZoneUsage.Residential;
        [Range(0f, 1f)] public float spawnWeight = 1f;
        public Vector2 heightMultiplier = new Vector2(0.6f, 1f);
        [Tooltip("Asset category names in the catalog eligible for this zone (e.g. 'building.house'). Empty = procedural buildings only.")]
        public string[] assetCategories = new string[0];
        [Tooltip("Scatter density for trees/lamps inside lots of this zone (0..1).")]
        [Range(0f, 1f)] public float greenery = 0.3f;
    }
}
