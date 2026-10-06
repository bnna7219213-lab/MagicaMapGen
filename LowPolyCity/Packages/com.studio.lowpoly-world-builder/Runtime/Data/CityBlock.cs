using System;
using System.Collections.Generic;
using UnityEngine;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>One rectangular city block between roads.</summary>
    [Serializable]
    public sealed class CityBlock
    {
        public Vector2Int coord;       // block lattice coordinate
        public Rect rect;              // world-space inner rect (sidewalk inset already applied)
        public Rect outerRect;         // including sidewalk ring
        public int zoneIndex;          // index into profile.zones
        public bool infrastructureBlock;
        public List<LotData> lots = new List<LotData>();
        public string RegionKey => $"block_{coord.x}_{coord.y}";
    }

    public enum LotFacing { North, East, South, West }

    /// <summary>One buildable parcel inside a block.</summary>
    [Serializable]
    public sealed class LotData
    {
        public Rect rect;
        public LotFacing facing;
        public BuildingArchetype archetype;
        public float height;
        public int wallColorIndex;
        public int roofColorIndex;
        public string assetCategory;   // non-empty -> place prefab instead of procedural mesh
        public bool manualLocked;
        public int subSeed;
        public float styleRoll;        // deterministic 0..1 for ornament variation
    }
}
