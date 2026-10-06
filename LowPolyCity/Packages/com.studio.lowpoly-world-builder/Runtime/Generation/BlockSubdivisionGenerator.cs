using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Splits the area between roads into blocks, assigns zones by weighted
    /// random, then carves lots along each block edge.
    /// </summary>
    public sealed class BlockSubdivisionGenerator : IWorldGenerator<WorldBuildProfile, List<CityBlock>>
    {
        public List<CityBlock> Generate(WorldBuildProfile profile, GenerationContext ctx)
        {
            var blocks = new List<CityBlock>();
            float pitch = profile.Pitch;
            float half = profile.roadWidth * 0.5f;
            float sw = profile.sidewalkWidth;

            for (int by = 0; by < profile.blockCount.y; by++)
            for (int bx = 0; bx < profile.blockCount.x; bx++)
            {
                float ox = half + bx * pitch + half; // outer edge of sidewalk ring
                float oz = half + by * pitch + half;
                var outer = new Rect(ox, oz, profile.blockSize, profile.blockSize);
                var inner = new Rect(ox + sw, oz + sw,
                    Mathf.Max(1f, profile.blockSize - 2f * sw),
                    Mathf.Max(1f, profile.blockSize - 2f * sw));

                var block = new CityBlock
                {
                    coord = new Vector2Int(bx, by),
                    outerRect = outer,
                    rect = inner,
                    zoneIndex = PickZone(profile, ctx, bx, by),
                    infrastructureBlock = IsInfrastructureBlock(profile, bx, by)
                };
                if (!block.infrastructureBlock) Subdivide(profile, block, ctx);
                blocks.Add(block);
            }

            ctx.Report.blockCount = blocks.Count;
            int lotCount = 0;
            foreach (var b in blocks) lotCount += b.lots.Count;
            ctx.Report.lotCount = lotCount;
            ctx.Report.Info("Blocks", $"{blocks.Count} blocks, {lotCount} lots");
            return blocks;
        }

        static bool IsInfrastructureBlock(WorldBuildProfile profile, int bx, int by)
        {
            if (profile.theme == WorldTheme.Airport)
                return by == 0 || (by == 1 && bx == 0); // runway strip and terminal apron
            if (profile.theme == WorldTheme.Harbor)
            {
                int harborWidth = Mathf.Min(profile.blockCount.x, Mathf.Max(2, profile.blockCount.x / 4));
                int harborHeight = Mathf.Min(profile.blockCount.y, Mathf.Max(2, profile.blockCount.y / 4));
                return bx >= profile.blockCount.x - harborWidth && by < harborHeight;
            }
            return false;
        }

        int PickZone(WorldBuildProfile profile, GenerationContext ctx, int bx, int by)
        {
            if (profile.zones == null || profile.zones.Length == 0) return -1;
            var sub = ctx.SubContext($"zone_{bx}_{by}").Random;
            var weights = new float[profile.zones.Length];
            bool anyNull = false;
            for (int i = 0; i < weights.Length; i++)
            {
                if (profile.zones[i] == null) { anyNull = true; weights[i] = 0f; continue; }
                weights[i] = profile.zones[i].spawnWeight;
            }
            int pick = sub.WeightedPick(weights);

            // Fix C3: Do not silently return -1 when zone resolution fails.
            // Report a readable error so the user sees what went wrong.
            if (anyNull)
                ctx.Report.Error("Zone", $"block ({bx},{by}) has null zone entries in profile");
            if (pick < 0 && !anyNull)
                ctx.Report.Error("Zone", $"block ({bx},{by}) zone pick failed (all weights <= 0)");

            return pick < 0 ? -1 : pick;
        }

        void Subdivide(WorldBuildProfile profile, CityBlock block, GenerationContext ctx)
        {
            var rand = ctx.SubContext(block.RegionKey).Random;
            float minLot = Mathf.Max(4f, profile.lotSizeRange.x);
            float maxLot = Mathf.Max(minLot, profile.lotSizeRange.y);

            // Carve lots along all four edges of the inner rect (perimeter lots,
            // facing outward to the street — reads well at cartoon scale).
            CarveEdge(profile, block, rand, LotFacing.North, minLot, maxLot);
            CarveEdge(profile, block, rand, LotFacing.South, minLot, maxLot);
            CarveEdge(profile, block, rand, LotFacing.East, minLot, maxLot);
            CarveEdge(profile, block, rand, LotFacing.West, minLot, maxLot);
        }

        void CarveEdge(WorldBuildProfile profile, CityBlock block, DeterministicRandom rand,
                       LotFacing facing, float minLot, float maxLot)
        {
            Rect r = block.rect;
            bool horizontal = facing == LotFacing.North || facing == LotFacing.South;
            float edgeLen = horizontal ? r.width : r.height;
            float depth = Mathf.Min(maxLot, (horizontal ? r.height : r.width) * 0.45f);
            if (depth < minLot) return;

            // Fix C2 (lot overlap): Vertical edges (East/West) start their cursor
            // at 'depth' and end at 'edgeLen - depth' so they never carve into the
            // corner strips reserved by the perpendicular North/South edges.
            // Horizontal edges (North/South) still run the full edge length.
            float cursor = 0f;
            float endPos = edgeLen;
            if (!horizontal)
            {
                cursor = depth;        // skip lower corner (South's strip)
                endPos = edgeLen - depth;  // skip upper corner (North's strip)
            }

            while (endPos - cursor >= minLot)
            {
                float remaining = endPos - cursor;
                float w = Mathf.Min(rand.NextFloat(minLot, maxLot), remaining);
                if (remaining - w < minLot) w = remaining; // absorb remainder

                Rect lot;
                switch (facing)
                {
                    case LotFacing.North: lot = new Rect(r.x + cursor, r.yMax - depth, w, depth); break;
                    case LotFacing.South: lot = new Rect(r.x + cursor, r.y, w, depth); break;
                    case LotFacing.East: lot = new Rect(r.xMax - depth, r.y + cursor, depth, w); break;
                    default: lot = new Rect(r.x, r.y + cursor, depth, w); break;
                }

                if (!rand.Chance(profile.lotFillRatio)) { cursor += w; continue; }

                block.lots.Add(new LotData
                {
                    rect = lot,
                    facing = facing,
                    subSeed = rand.NextInt(0, int.MaxValue)
                });
                cursor += w;
            }
        }
    }
}
