using System;
using System.Collections.Generic;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>
    /// Output of the rule/domain layer: everything the geometry/assembly
    /// layers need, no GameObjects. Serializable so it can be diffed.
    /// </summary>
    [Serializable]
    public sealed class BuildPlan
    {
        public int schemaVersion = 1;
        public int seed;
        public string generatorVersion = "0.3.0";
        public RoadGraph roadGraph = new RoadGraph();
        public List<CityBlock> blocks = new List<CityBlock>();
        public List<ScatterItem> scatter = new List<ScatterItem>();
    }

    [Serializable]
    public sealed class ScatterItem
    {
        public string category;        // 'prop.tree', 'prop.lamp'
        public UnityEngine.Vector3 position;
        public float rotationY;
        public float scale;
    }
}
