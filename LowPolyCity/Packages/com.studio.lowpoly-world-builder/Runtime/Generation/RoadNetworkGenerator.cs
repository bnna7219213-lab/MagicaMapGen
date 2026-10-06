using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Builds the parametric grid road graph. Node degree decides junction
    /// type (corner / T / cross) — topology-driven, not random decoration.
    /// </summary>
    public sealed class RoadNetworkGenerator : IWorldGenerator<WorldBuildProfile, RoadGraph>
    {
        public RoadGraph Generate(WorldBuildProfile profile, GenerationContext ctx)
        {
            var g = new RoadGraph();
            var nodes = profile.GridNodeCount;
            float pitch = profile.Pitch;
            float half = profile.roadWidth * 0.5f;

            // Node lattice: node (i,j) is the CENTER of the intersection at the
            // corner of blocks; world origin is the outer road edge.
            var idx = new int[nodes.x, nodes.y];
            for (int j = 0; j < nodes.y; j++)
            for (int i = 0; i < nodes.x; i++)
            {
                var pos = new Vector3(half + i * pitch, 0f, half + j * pitch);
                idx[i, j] = g.AddNode(new Vector2Int(i, j), pos);
            }

            for (int j = 0; j < nodes.y; j++)
            for (int i = 0; i < nodes.x; i++)
            {
                if (i + 1 < nodes.x) g.AddEdge(idx[i, j], idx[i + 1, j], profile.roadWidth);
                if (j + 1 < nodes.y) g.AddEdge(idx[i, j], idx[i, j + 1], profile.roadWidth);
            }

            if (!g.IsConnected(out int orphans))
                ctx.Report.Error("RoadNetwork", $"{orphans} road nodes disconnected");
            ctx.Report.Info("RoadNetwork", $"{g.edges.Count} road segments, {g.nodes.Count} intersections");
            ctx.Report.roadSegmentCount = g.edges.Count;
            return g;
        }
    }
}
