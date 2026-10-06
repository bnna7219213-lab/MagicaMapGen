using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Ground plane + simple height variation hook. MVP: flat ground quad per
    /// world; the height hook is where a heightfield enters in phase 4.
    /// </summary>
    public sealed class TerrainGenerator
    {
        public float SampleHeight(Vector2 xz)
        {
            return 0f; // flat MVP; replace with heightfield sampling later
        }
    }
}
