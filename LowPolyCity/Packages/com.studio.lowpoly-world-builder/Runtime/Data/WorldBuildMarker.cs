using UnityEngine;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>
    /// Placed on every generated root node. Rebuild/cleanup only ever touches
    /// objects carrying this marker, so user content is never deleted
    /// (plan 5.3). Set manualLock to protect a generated subtree.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class WorldBuildMarker : MonoBehaviour
    {
        public string profileGuid;
        public int seed;
        public string regionKey = "world";
        public string pluginVersion = "0.1.0";
        public bool manualLock;
    }
}
