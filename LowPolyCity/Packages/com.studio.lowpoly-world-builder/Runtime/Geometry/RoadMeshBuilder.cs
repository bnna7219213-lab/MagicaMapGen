using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Geometry
{
    /// <summary>
    /// Submesh slots for the road mesh:
    /// 0 = asphalt, 1 = markings, 2 = sidewalk, 3 = ground.
    /// </summary>
    public static class RoadSubmeshes
    {
        public const int Asphalt = 0;
        public const int Markings = 1;
        public const int Sidewalk = 2;
        public const int Ground = 3;
        public const int Count = 4;
    }

    /// <summary>
    /// Builds the whole road network as ONE mesh: per-edge asphalt strips,
    /// intersection squares, center dashes, sidewalk rings per block and the
    /// world ground quad. Single mesh keeps object count flat for the MVP.
    /// </summary>
    public sealed class RoadMeshBuilder
    {
        public Mesh Build(RoadGraph graph, float sidewalkWidth, float worldSizeX, float worldSizeZ,
                          System.Collections.Generic.List<CityBlock> blocks, string name)
        {
            var mb = new MeshBuilder();
            const float yRoad = 0.05f, yMark = 0.08f, yWalk = 0.12f;

            // Ground
            mb.AddQuad(RoadSubmeshes.Ground,
                new Vector3(0, 0, 0), new Vector3(worldSizeX, 0, 0),
                new Vector3(worldSizeX, 0, worldSizeZ), new Vector3(0, 0, worldSizeZ),
                Vector3.up);

            // Sidewalk ring per block (outer rect minus inner rect -> 4 strips)
            foreach (var b in blocks)
            {
                var o = b.outerRect; var ir = b.rect;
                AddStrip(mb, new Rect(o.x, o.y, o.width, ir.y - o.y), yWalk);                       // south
                AddStrip(mb, new Rect(o.x, ir.yMax, o.width, o.yMax - ir.yMax), yWalk);            // north
                AddStrip(mb, new Rect(o.x, ir.y, ir.x - o.x, ir.height), yWalk);                   // west
                AddStrip(mb, new Rect(ir.xMax, ir.y, o.xMax - ir.xMax, ir.height), yWalk);         // east
            }

            // Road strips + dashes
            foreach (var e in graph.edges)
            {
                if (!e.active) continue;
                Vector3 pa = graph.nodes[e.a].position, pb = graph.nodes[e.b].position;
                Vector3 dir = (pb - pa).normalized;
                Vector3 side = Vector3.Cross(Vector3.up, dir) * (e.width * 0.5f);
                mb.AddQuad(RoadSubmeshes.Asphalt,
                    pa - side + Vector3.up * yRoad, pa + side + Vector3.up * yRoad,
                    pb + side + Vector3.up * yRoad, pb - side + Vector3.up * yRoad, Vector3.up);

                // center dashes
                float len = Vector3.Distance(pa, pb);
                const float dash = 3f, gap = 3f, dashW = 0.25f;
                for (float t = gap; t + dash < len; t += dash + gap)
                {
                    Vector3 c0 = pa + dir * t, c1 = pa + dir * (t + dash);
                    Vector3 sw = Vector3.Cross(Vector3.up, dir) * (dashW * 0.5f);
                    mb.AddQuad(RoadSubmeshes.Markings,
                        c0 - sw + Vector3.up * yMark, c0 + sw + Vector3.up * yMark,
                        c1 + sw + Vector3.up * yMark, c1 - sw + Vector3.up * yMark, Vector3.up);
                }
            }

            // Intersection asphalt squares
            foreach (var n in graph.nodes)
            {
                if (n.edges.Count == 0) continue;
                float h = 0f;
                foreach (var ei in n.edges) h = Mathf.Max(h, graph.edges[ei].width);
                h *= 0.5f;
                var c = n.position;
                mb.AddQuad(RoadSubmeshes.Asphalt,
                    c + new Vector3(-h, yRoad, -h), c + new Vector3(h, yRoad, -h),
                    c + new Vector3(h, yRoad, h), c + new Vector3(-h, yRoad, h), Vector3.up);
            }

            return mb.Build(name);
        }

        static void AddStrip(MeshBuilder mb, Rect r, float y)
        {
            if (r.width <= 0.01f || r.height <= 0.01f) return;
            mb.AddQuad(RoadSubmeshes.Sidewalk,
                new Vector3(r.xMin, y, r.yMin), new Vector3(r.xMax, y, r.yMin),
                new Vector3(r.xMax, y, r.yMax), new Vector3(r.xMin, y, r.yMax), Vector3.up);
        }
    }
}
