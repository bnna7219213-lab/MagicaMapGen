using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Scatters trees along sidewalk rings and lamps at intersections.
    /// Placement is constrained by the road graph (lamps) and zone greenery
    /// (trees). Slope/water constraints hook in with the heightfield later.
    /// </summary>
    public sealed class ScatterGenerator
    {
        public List<ScatterItem> Generate(WorldBuildProfile profile, RoadGraph graph,
                                          List<CityBlock> blocks, GenerationContext ctx)
        {
            var items = new List<ScatterItem>();

            // Lamps at every intersection corner offset.
            var randLamp = ctx.SubContext("scatter_lamps").Random;
            foreach (var node in graph.nodes)
            {
                if (node.edges.Count < 2) continue;
                float off = profile.roadWidth * 0.5f + profile.sidewalkWidth * 0.5f;
                items.Add(new ScatterItem
                {
                    category = "prop.lamp",
                    position = node.position + new Vector3(off, 0f, off),
                    rotationY = randLamp.NextInt(0, 4) * 90f,
                    scale = 1f
                });
            }

            // Trees on the sidewalk ring, density from zone greenery.
            foreach (var block in blocks)
            {
                if (block.infrastructureBlock) continue;
                ZoneProfile zone = null;
                if (profile.zones != null && block.zoneIndex >= 0 && block.zoneIndex < profile.zones.Length)
                    zone = profile.zones[block.zoneIndex];

                // Themed prop substitution: industrial/rail areas get tanks and
                // poles instead of cartoon trees.
                string propCategory = "prop.tree";
                float greenery = zone != null ? zone.greenery : 0.3f;
                if (zone != null)
                {
                    switch (zone.usage)
                    {
                        case ZoneUsage.Industrial:
                        case ZoneUsage.Harbor:
                            propCategory = "prop.tank"; greenery *= 0.8f; break;
                        case ZoneUsage.Rail:
                            propCategory = "prop.pole"; greenery *= 0.7f; break;
                    }
                }
                if (greenery <= 0f) continue;

                var rand = ctx.SubContext("scatter_trees_" + block.RegionKey).Random;
                const float step = 14f;
                for (float x = block.outerRect.xMin + 2f; x < block.outerRect.xMax - 2f; x += step)
                for (float z = block.outerRect.yMin + 2f; z < block.outerRect.yMax - 2f; z += step)
                {
                    bool onSidewalk = x < block.rect.xMin || x > block.rect.xMax ||
                                      z < block.rect.yMin || z > block.rect.yMax;
                    if (!onSidewalk) continue; // keep props on the sidewalk ring
                    if (!rand.Chance(greenery * 0.5f)) continue;
                    items.Add(new ScatterItem
                    {
                        category = propCategory,
                        position = new Vector3(x + rand.NextFloat(-2f, 2f), 0f, z + rand.NextFloat(-2f, 2f)),
                        rotationY = rand.NextFloat(0f, 360f),
                        scale = rand.NextFloat(0.8f, 1.3f)
                    });
                }
            }

            ctx.Report.scatterCount = items.Count;
            ctx.Report.Info("Scatter", $"{items.Count} scatter items (trees/lamps)");
            return items;
        }
    }
}
