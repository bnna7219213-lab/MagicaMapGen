using UnityEngine;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>
    /// Identity tag placed on every GameObject the map builder instantiates from a
    /// map.json instance. It is the join key for the phase-3 edit round-trip:
    /// <c>SceneDiffer</c> reads these off the live scene, compares them against the
    /// source document, and derives delete / move / add ops.
    ///
    /// <see cref="SpawnedWorld"/> records where the object was placed at build time,
    /// so a later transform edit is detected as a move by comparing against it rather
    /// than against a re-derived value.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class MapInstanceId : MonoBehaviour
    {
        public int Id = -1;
        public string Category = "";
        public string Type = "";
        /// <summary>"auto" | "user-added" | "user-moved" (schema v4).</summary>
        public string Source = "auto";
        public int OrigCellX;
        public int OrigCellY;
        public Vector3 SpawnedWorld;
        public double RotationDegrees;
        public double Scale = 1.0;

        public void Configure(MapInstance inst)
        {
            Id = inst.Id;
            Category = inst.Category;
            Type = inst.Type;
            Source = string.IsNullOrEmpty(inst.Source) ? "auto" : inst.Source;
            OrigCellX = inst.X;
            OrigCellY = inst.Y;
            SpawnedWorld = new Vector3(
                (float)inst.World[0], (float)inst.World[1], (float)inst.World[2]);
            RotationDegrees = inst.RotationDegrees;
            Scale = inst.Scale;
        }
    }
}
