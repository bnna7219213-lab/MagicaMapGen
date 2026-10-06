using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace IslandMapGenerator
{
    /// <summary>
    /// Island Map Generator - Prototype design tool for game development.
    /// Generates procedurally diverse island terrains with probability-driven
    /// features: mountain ranges, valleys, basins, grasslands, forests, rivers.
    /// Deterministic by seed (same seed + parameters => identical result).
    /// </summary>
    public static class IslandGeneratorCore
    {
        public struct IslandConfig
        {
            public int Width;
            public int Height;
            public float IslandRadius;
            public float MountainFrequency;
            public float DetailFrequency;
            public int ValleyCount;
            public int RiverCount;
            public float SeaLevel;
            public float TreeDensity;
            public float GrassDensity;
            public float RockDensity;
            public float BeachWidth;
            public float WarpStrength;
            public int NoiseOctaves;
            public float Persistence;
            public float Lacunarity;

            public static IslandConfig Default(int w = 512, int h = 512) => new IslandConfig
            {
                Width = w, Height = h,
                IslandRadius = 0.42f,
                MountainFrequency = 0.9f,
                DetailFrequency = 4.5f,
                ValleyCount = 3,
                RiverCount = 5,
                SeaLevel = 0.32f,
                TreeDensity = 0.6f,
                GrassDensity = 0.5f,
                RockDensity = 0.3f,
                BeachWidth = 0.06f,
                WarpStrength = 0.18f,
                NoiseOctaves = 5,
                Persistence = 0.55f,
                Lacunarity = 2.05f
            };
        }

        public struct IslandData
        {
            public IslandConfig Config;
            public int Seed;
            public float[,] Height;
            public float[,] Moisture;
            public BiomeId[,] Biome;
            public float[,] River;
            public List<ScatterItem> Scatter;
            public float SeaLevel;
            public float MaxHeight;
            public int BeachCells, GrassCells, ForestCells, RockCells, PeakCells, WaterCells;
            public int RiverCells;
            public int TreeCount, RockCount, DetailCount;
        }

        public enum BiomeId : byte
        {
            DeepWater = 0, ShallowWater = 1, Beach = 2, Grassland = 3,
            Forest = 4, Rocky = 5, Peak = 6, ValleyBasin = 7
        }

        public struct ScatterItem
        {
            public float X, Y;
            public float Scale;
            public ScatterType Type;
            public float Rotation;
        }

        public enum ScatterType : byte
        {
            Tree, Rock, GrassTuft, Reed, Detail
        }

        public sealed class DetRandom
        {
            ulong _s0, _s1;
            public DetRandom(int seed)
            {
                ulong z = (ulong)seed + 0x9E3779B97F4A7C15ul;
                _s0 = Mix(ref z); _s1 = Mix(ref z);
                if (_s0 == 0 && _s1 == 0) _s1 = 1;
            }
            static ulong Mix(ref ulong z)
            {
                z += 0x9E3779B97F4A7C15ul;
                ulong x = z;
                x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ul;
                x = (x ^ (x >> 27)) * 0x94D049BB133111EBul;
                return x ^ (x >> 31);
            }
            ulong NextUlong()
            {
                ulong s1 = _s0, s0 = _s1;
                _s0 = s0;
                s1 ^= s1 << 23;
                _s1 = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
                return _s1 + s0;
            }
            public float NextFloat(float min, float max)
            {
                float t = (float)(NextUlong() >> 11) * (1f / 9007199254740992f);
                return min + (max - min) * t;
            }
            public int NextInt(int minInclusive, int maxExclusive)
            {
                if (maxExclusive <= minInclusive) return minInclusive;
                ulong span = (ulong)(maxExclusive - minInclusive);
                return minInclusive + (int)(NextUlong() % span);
            }
            public bool Chance(float p) => NextFloat(0f, 1f) < p;
        }

        static float Hash2D(int x, int y, int seed)
        {
            unchecked
            {
                uint h = (uint)seed;
                h ^= (uint)(x * 374761393);
                h ^= (uint)(y * 668265263);
                h = (h ^ (h >> 13)) * 1274126177;
                h ^= h >> 16;
                return (h & 0xFFFFFF) / 16777215f;
            }
        }

        static float SmoothNoise(float x, float y, int seed)
        {
            int ix = (int)Math.Floor(x);
            int iy = (int)Math.Floor(y);
            float fx = x - ix;
            float fy = y - iy;
            fx = fx * fx * (3 - 2 * fx);
            fy = fy * fy * (3 - 2 * fy);
            float a = Hash2D(ix, iy, seed);
            float b = Hash2D(ix + 1, iy, seed);
            float c = Hash2D(ix, iy + 1, seed);
            float d = Hash2D(ix + 1, iy + 1, seed);
            float ab = a + (b - a) * fx;
            float cd = c + (d - c) * fx;
            return ab + (cd - ab) * fy;
        }

        static float Fbm(float x, float y, int seed, int octaves, float persistence, float lacunarity)
        {
            float amp = 1f, freq = 1f, sum = 0f, norm = 0f;
            for (int o = 0; o < octaves; o++)
            {
                sum += amp * SmoothNoise(x * freq, y * freq, seed + o * 1013);
                norm += amp;
                amp *= persistence;
                freq *= lacunarity;
            }
            return sum / norm;
        }

        static float Ridged(float x, float y, int seed, int octaves, float persistence, float lacunarity)
        {
            float amp = 1f, freq = 1f, sum = 0f, norm = 0f;
            for (int o = 0; o < octaves; o++)
            {
                float n = SmoothNoise(x * freq, y * freq, seed + o * 2017);
                n = 1f - Math.Abs(n * 2f - 1f);
                n = n * n;
                sum += amp * n;
                norm += amp;
                amp *= persistence;
                freq *= lacunarity;
            }
            return sum / norm;
        }

        static float ValleyCarve(float x, float y, List<(float cx, float cy, float r, float depth)> basins)
        {
            float v = 1f;
            foreach (var b in basins)
            {
                float dx = (x - b.cx);
                float dy = (y - b.cy);
                float d2 = dx * dx + dy * dy;
                float r2 = b.r * b.r;
                float falloff = Math.Max(0f, 1f - d2 / r2);
                falloff = falloff * falloff * (3 - 2 * falloff);
                v -= falloff * b.depth;
            }
            return Math.Max(0f, v);
        }

        public static IslandData Generate(int seed, IslandConfig cfg)
        {
            var rng = new DetRandom(seed);
            var data = new IslandData
            {
                Config = cfg,
                Seed = seed,
                Height = new float[cfg.Width, cfg.Height],
                Moisture = new float[cfg.Width, cfg.Height],
                Biome = new BiomeId[cfg.Width, cfg.Height],
                River = new float[cfg.Width, cfg.Height],
                Scatter = new List<ScatterItem>(),
                SeaLevel = cfg.SeaLevel
            };

            var basins = new List<(float cx, float cy, float r, float depth)>();
            for (int i = 0; i < cfg.ValleyCount; i++)
            {
                basins.Add((
                    rng.NextFloat(0.25f, 0.75f),
                    rng.NextFloat(0.25f, 0.75f),
                    rng.NextFloat(0.18f, 0.38f),
                    rng.NextFloat(0.15f, 0.35f)
                ));
            }

            float maxH = 0f;
            for (int y = 0; y < cfg.Height; y++)
            {
                for (int x = 0; x < cfg.Width; x++)
                {
                    float u = x / (float)cfg.Width;
                    float v = y / (float)cfg.Height;

                    float wx = Fbm(u * cfg.MountainFrequency, v * cfg.MountainFrequency, seed + 7, 4, 0.5f, 2.0f);
                    float wy = Fbm(u * cfg.MountainFrequency + 5.2f, v * cfg.MountainFrequency + 1.3f, seed + 19, 4, 0.5f, 2.0f);
                    float wu = u + (wx - 0.5f) * cfg.WarpStrength;
                    float wv = v + (wy - 0.5f) * cfg.WarpStrength;

                    float ridge = Ridged(wu * cfg.MountainFrequency * 3.0f, wv * cfg.MountainFrequency * 3.0f,
                                         seed + 31, cfg.Noctaves, cfg.Persistence, cfg.Lacunarity);

                    float detail = SmoothNoise(u * cfg.DetailFrequency * 8f, v * cfg.DetailFrequency * 8f, seed + 777);
                    float valley = ValleyCarve(u, v, basins);

                    float h = ridge * 0.75f + detail * 0.08f;
                    h *= valley;
                    h += SmoothNoise(u * 30f, v * 30f, seed + 9999) * 0.015f;

                    float nx = (x / (float)cfg.Width - 0.5f) * 2f;
                    float ny = (y / (float)cfg.Height - 0.5f) * 2f;
                    float cwarp = Fbm(u * 2.5f + wx * 0.3f, v * 2.5f + wy * 0.3f, seed + 444, 3, 0.6f, 2.0f);
                    float dist = (float)Math.Sqrt(nx * nx + ny * ny);
                    dist += (cwarp - 0.5f) * 0.25f;
                    float mask = 1f - SmoothStep(cfg.IslandRadius * 0.75f, cfg.IslandRadius * 1.15f, dist);

                    h *= mask;
                    h = Math.Clamp(h, 0f, 1f);
                    data.Height[x, y] = h;
                    if (h > maxH) maxH = h;
                }
            }
            data.MaxHeight = maxH > 0 ? maxH : 1f;

            for (int y = 0; y < cfg.Height; y++)
            {
                for (int x = 0; x < cfg.Width; x++)
                {
                    float hgt = data.Height[x, y];
                    float m = (hgt < cfg.SeaLevel) ? 0.7f : 1f - SmoothStep(0f, 1f, hgt);
                    float u = x / (float)cfg.Width;
                    float v = y / (float)cfg.Height;
                    m += SmoothNoise(u * 5f, v * 5f, seed + 5555) * 0.25f;
                    data.Moisture[x, y] = Math.Clamp(m, 0f, 1f);
                }
            }

            AssignBiomes(data, rng);
            GenerateRivers(data, rng);
            GenerateScatter(data, rng);
            ComputeStats(data);

            return data;
        }

        static void AssignBiomes(IslandData data, DetRandom rng)
        {
            for (int y = 0; y < data.Config.Height; y++)
            {
                for (int x = 0; x < data.Config.Width; x++)
                {
                    float h = data.Height[x, y];
                    float m = data.Moisture[x, y];
                    float beachBoundary = data.SeaLevel + data.Config.BeachWidth;
                    BiomeId b;
                    if (h < data.SeaLevel - 0.04f) b = BiomeId.DeepWater;
                    else if (h < data.SeaLevel) b = BiomeId.ShallowWater;
                    else if (h < beachBoundary) b = BiomeId.Beach;
                    else if (h > 0.82f) b = BiomeId.Peak;
                    else if (h > 0.65f) b = BiomeId.Rocky;
                    else if (h < data.SeaLevel + 0.18f && m > 0.5f)
                        b = BiomeId.ValleyBasin;
                    else if (m > 0.45f && h < 0.65f)
                        b = BiomeId.Forest;
                    else
                        b = BiomeId.Grassland;

                    data.Biome[x, y] = b;
                }
            }
        }

        static void GenerateRivers(IslandData data, DetRandom rng)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;
            var flow = new float[w, h];
            int riverTries = Math.Max(data.Config.RiverCount * 4, 12);
            int acceptedRivers = 0;

            for (int attempt = 0; attempt < riverTries && acceptedRivers < data.Config.RiverCount; attempt++)
            {
                int bestX = -1, bestY = -1;
                float bestH = 0f;
                for (int probe = 0; probe < 60; probe++)
                {
                    int px = rng.NextInt(4, w - 4);
                    int py = rng.NextInt(4, h - 4);
                    float hgt = data.Height[px, py];
                    if (hgt > 0.55f && hgt > bestH && data.Biome[px, py] != BiomeId.DeepWater && data.Biome[px, py] != BiomeId.ShallowWater)
                    {
                        bestH = hgt; bestX = px; bestY = py;
                    }
                }
                if (bestX < 0) continue;

                int cx = bestX, cy = bestY;
                int steps = 0;
                int maxSteps = w + h;
                bool reachedSea = false;
                while (steps < maxSteps)
                {
                    flow[cx, cy] += 1f;
                    if (data.Height[cx, cy] < data.SeaLevel) { reachedSea = true; break; }
                    int nx = cx, ny = cy;
                    float lowest = data.Height[cx, cy];
                    for (int oy = -1; oy <= 1; oy++)
                        for (int ox = -1; ox <= 1; ox++)
                        {
                            if (ox == 0 && oy == 0) continue;
                            int tx = cx + ox, ty = cy + oy;
                            if (tx < 0 || ty < 0 || tx >= w || ty >= h) continue;
                            float ngh = data.Height[tx, ty] + rng.NextFloat(0f, 0.003f);
                            if (ngh < lowest) { lowest = ngh; nx = tx; ny = ty; }
                        }
                    if (nx == cx && ny == cy) break;
                    cx = nx; cy = ny;
                    steps++;

                    if (rng.Chance(0.06f))
                    {
                        int bx = cx + rng.NextInt(-1, 2);
                        int by = cy + rng.NextInt(-1, 2);
                        if (bx >= 0 && by >= 0 && bx < w && by < h)
                            flow[bx, by] += 0.4f;
                    }
                }
                if (reachedSea && steps > 20) acceptedRivers++;
            }

            float maxFlow = 0f;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    if (flow[x, y] > maxFlow) maxFlow = flow[x, y];

            if (maxFlow > 0)
            {
                for (int y = 0; y < h; y++)
                    for (int x = 0; x < w; x++)
                        data.River[x, y] = flow[x, y] / maxFlow;
            }
        }

        static void GenerateScatter(IslandData data, DetRandom rng)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;
            int totalScatterBudget = (int)(w * h * 0.012f);
            int placed = 0;
            int attempts = 0;
            int maxAttempts = totalScatterBudget * 20;

            while (placed < totalScatterBudget && attempts < maxAttempts)
            {
                attempts++;
                int x = rng.NextInt(0, w);
                int y = rng.NextInt(0, h);
                var b = data.Biome[x, y];
                float hgt = data.Height[x, y];
                float slope = SampleSlope(data, x, y);

                ScatterType type;
                float p;
                if (b == BiomeId.Forest && slope < 0.4f)
                {
                    p = 0.9f * data.Config.TreeDensity;
                    type = ScatterType.Tree;
                }
                else if (b == BiomeId.Grassland && slope < 0.3f)
                {
                    p = rng.Chance(0.5f) ? 0.7f * data.Config.GrassDensity : 0.4f * data.Config.TreeDensity;
                    type = rng.Chance(0.5f) ? ScatterType.GrassTuft : ScatterType.Tree;
                }
                else if (b == BiomeId.Rocky || b == BiomeId.Peak)
                {
                    p = 0.85f * data.Config.RockDensity;
                    type = ScatterType.Rock;
                }
                else if (b == BiomeId.ValleyBasin)
                {
                    p = 0.6f * data.Config.GrassDensity * 1.2f;
                    type = rng.Chance(0.4f) ? ScatterType.Reed : ScatterType.GrassTuft;
                }
                else if (b == BiomeId.Beach)
                {
                    p = 0.1f;
                    type = ScatterType.Rock;
                }
                else if (b == BiomeId.DeepWater || b == BiomeId.ShallowWater)
                {
                    continue;
                }
                else { continue; }

                if (data.River[x, y] > 0.3f && type != ScatterType.Rock && rng.Chance(0.4f))
                    type = ScatterType.Reed;

                if (!rng.Chance(p)) continue;

                data.Scatter.Add(new ScatterItem
                {
                    X = x / (float)w,
                    Y = y / (float)h,
                    Scale = rng.NextFloat(0.6f, 1.3f),
                    Type = type,
                    Rotation = rng.NextFloat(0f, 360f)
                });
                placed++;
            }
        }

        static float SampleSlope(IslandData data, int x, int y)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;
            float hl = data.Height[Math.Max(0, x - 1), y];
            float hr = data.Height[Math.Min(w - 1, x + 1), y];
            float hd = data.Height[x, Math.Max(0, y - 1)];
            float hu = data.Height[x, Math.Min(h - 1, y + 1)];
            float dx = hr - hl;
            float dy = hu - hd;
            return (float)Math.Sqrt(dx * dx + dy * dy) * 0.5f;
        }

        static void ComputeStats(IslandData data)
        {
            int beach = 0, grass = 0, forest = 0, rock = 0, peak = 0, water = 0, valley = 0, river = 0;
            int trees = 0, rocks = 0, details = 0;
            for (int y = 0; y < data.Config.Height; y++)
            {
                for (int x = 0; x < data.Config.Width; x++)
                {
                    switch (data.Biome[x, y])
                    {
                        case BiomeId.DeepWater: case BiomeId.ShallowWater: water++; break;
                        case BiomeId.Beach: beach++; break;
                        case BiomeId.Grassland: grass++; break;
                        case BiomeId.Forest: forest++; break;
                        case BiomeId.Rocky: rock++; break;
                        case BiomeId.Peak: peak++; break;
                        case BiomeId.ValleyBasin: valley++; break;
                    }
                    if (data.River[x, y] > 0.15f) river++;
                }
            }
            foreach (var s in data.Scatter)
            {
                switch (s.Type)
                {
                    case ScatterType.Tree: trees++; break;
                    case ScatterType.Rock: rocks++; break;
                    default: details++; break;
                }
            }
            data.BeachCells = beach;
            data.GrassCells = grass;
            data.ForestCells = forest;
            data.RockCells = rock;
            data.PeakCells = peak;
            data.WaterCells = water;
            data.RiverCells = river;
            data.TreeCount = trees;
            data.RockCount = rocks;
            data.DetailCount = details;
        }

        static float SmoothStep(float a, float b, float x)
        {
            float t = Math.Clamp((x - a) / (b - a), 0f, 1f);
            return t * t * (3 - 2 * t);
        }
    }

    public static class MapIO
    {
        public static void WriteHeightmapPGM(IslandGeneratorCore.IslandData data, string path)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;
            using var fs = File.Create(path);
            var hdr = Encoding.ASCII.GetBytes($"P5\n{w} {h}\n65535\n");
            fs.Write(hdr, 0, hdr.Length);
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    ushort v = (ushort)Math.Clamp(data.Height[x, y] * 65535f, 0, 65535);
                    var bytes = new[] { (byte)(v >> 8), (byte)(v & 0xFF) };
                    fs.Write(bytes, 0, 2);
                }
        }

        public static void WriteBiomeCSV(IslandGeneratorCore.IslandData data, string path)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;
            var sb = new StringBuilder();
            sb.AppendLine("x,y,height,moisture,biome_id,river");
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    sb.AppendLine($"{x},{y},{data.Height[x, y]:F4},{data.Moisture[x, y]:F4},{(int)data.Biome[x, y]},{data.River[x, y]:F4}");
            File.WriteAllText(path, sb.ToString());
        }

        public static void WriteScatterCSV(IslandGeneratorCore.IslandData data, string path)
        {
            var sb = new StringBuilder();
            sb.AppendLine("x,y,type,scale,rotation");
            foreach (var s in data.Scatter)
                sb.AppendLine($"{s.X:F5},{s.Y:F5},{(int)s.Type},{s.Scale:F3},{s.Rotation:F1}");
            File.WriteAllText(path, sb.ToString());
        }

        public static void WriteReportJson(IslandGeneratorCore.IslandData data, string path)
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine($@"  ""seed"": {data.Seed},");
            sb.AppendLine($@"  ""width"": {data.Config.Width},");
            sb.AppendLine($@"  ""height"": {data.Config.Height},");
            sb.AppendLine($@"  ""islandRadius"": {data.Config.IslandRadius:F3},");
            sb.AppendLine($@"  ""mountainFrequency"": {data.Config.MountainFrequency:F3},");
            sb.AppendLine($@"  ""valleyCount"": {data.Config.ValleyCount},");
            sb.AppendLine($@"  ""riverCount"": {data.Config.RiverCount},");
            sb.AppendLine($@"  ""seaLevel"": {data.Config.SeaLevel:F3},");
            sb.AppendLine($@"  ""stats"": {{");
            sb.AppendLine($@"    ""totalCells"": {data.Config.Width * data.Config.Height},");
            sb.AppendLine($@"    ""waterCells"": {data.WaterCells},");
            sb.AppendLine($@"    ""beachCells"": {data.BeachCells},");
            sb.AppendLine($@"    ""grassCells"": {data.GrassCells},");
            sb.AppendLine($@"    ""forestCells"": {data.ForestCells},");
            sb.AppendLine($@"    ""rockCells"": {data.RockCells},");
            sb.AppendLine($@"    ""peakCells"": {data.PeakCells},");
            sb.AppendLine($@"    ""riverCells"": {data.RiverCells},");
            sb.AppendLine($@"    ""scatterCount"": {data.Scatter.Count},");
            sb.AppendLine($@"    ""treeCount"": {data.TreeCount},");
            sb.AppendLine($@"    ""rockCount"": {data.RockCount},");
            sb.AppendLine($@"    ""detailCount"": {data.DetailCount},");
            sb.AppendLine($@"    ""maxNormalizedHeight"": {data.MaxHeight:F4}");
            sb.AppendLine(@"  }");
            sb.AppendLine(@"}");
            File.WriteAllText(path, sb.ToString());
        }

        public static void WriteHtmlPreview(IslandGeneratorCore.IslandData data, string path)
        {
            int w = data.Config.Width;
            int h = data.Config.Height;

            // BuildHeightMap JSON
            var hsb = new StringBuilder();
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    hsb.Append(data.Height[x, y].ToString("F4", System.Globalization.CultureInfo.InvariantCulture));
                    if (x < w - 1) hsb.Append(",");
                }
                if (y < h - 1) hsb.Append(";");
            }

            // Build BiomeMap JSON
            var bsb = new StringBuilder();
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    bsb.Append((int)data.Biome[x, y]);
                    if (x < w - 1) bsb.Append(",");
                }
                if (y < h - 1) bsb.Append(";");
            }

            // Build RiverMap JSON
            var rsb = new StringBuilder();
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    rsb.Append(data.River[x, y].ToString("F4", System.Globalization.CultureInfo.InvariantCulture));
                    if (x < w - 1) rsb.Append(",");
                }
                if (y < h - 1) rsb.Append(";");
            }

            // Build Scatter JSON
            var ssb = new StringBuilder();
            for (int i = 0; i < data.Scatter.Count; i++)
            {
                var s = data.Scatter[i];
                if (i > 0) ssb.Append(";");
                ssb.Append(s.X.ToString("F4", System.Globalization.CultureInfo.InvariantCulture)).Append(",");
                ssb.Append(s.Y.ToString("F4", System.Globalization.CultureInfo.InvariantCulture)).Append(",");
                ssb.Append((int)s.Type).Append(",");
                ssb.Append(s.Scale.ToString("F3", System.Globalization.CultureInfo.InvariantCulture)).Append(",");
                ssb.Append(s.Rotation.ToString("F1", System.Globalization.CultureInfo.InvariantCulture));
            }

            int totalCells = data.Config.Width * data.Config.Height;
            float waterPct = data.WaterCells * 100.0f / totalCells;
            float beachPct = data.BeachCells * 100.0f / totalCells;
            float grassPct = data.GrassCells * 100.0f / totalCells;
            float forestPct = data.ForestCells * 100.0f / totalCells;
            float rockPct = data.RockCells * 100.0f / totalCells;
            float peakPct = data.PeakCells * 100.0f / totalCells;

            string html = @"<!DOCTYPE html>
<html><head><meta charset=""utf-8""><title>Island Map Generator - Prototype</title>
<style>
body{margin:0;background:#1a1a2e;color:#eee;font-family:system-ui,sans-serif;font-size:13px}
#wrap{display:grid;grid-template-columns:1fr 320px;gap:12px;padding:12px;height:100vh;box-sizing:border-box}
#canvasWrap{position:relative;background:#000;border:1px solid #333;display:flex;align-items:center;justify-content:center;overflow:hidden}
canvas{image-rendering:pixelated;max-width:100%;max-height:100%}
#panel{background:#16213e;padding:14px;border-radius:6px;overflow-y:auto;line-height:1.6em}
h2{margin-top:0;color:#e94560;font-size:16px}
h3{color:#53a8d8;font-size:13px;margin:14px 0 6px}
label{display:block;margin:4px 0}
input[type=range]{width:180px;vertical-align:middle}
button{background:#e94560;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer}
button:hover{background:#c0392b}
.stat-row{display:flex;justify-content:space-between;border-bottom:1px dashed #2a3a5a;padding:2px 0}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;margin-right:4px}
.b-water{background:#1a3a6a}
.b-beach:{background:#dcd2a0;color:#333}
.b-grass:{background:#78b45a}
.b-forest:{background:#287a3c}
.b-rock:{background:#827474}
.b-peak:{background:#dde1eb;color:#333}
.b-river:{background:#3a78cc}
#legend{margin-top:10px;padding-top:8px;border-top:1px solid #2a3a5a}
</style></head><<body>
<div id=""wrap"">
<div id=""canvasWrap""><canvas id=""cw""></canvas></div>
<div id=""panel"">
<h2>Island Map Generator</h2>
<b>Seed:</b> " + data.Seed + @"<br>
<b>Size:</b> " + w + "x" + h + @"<br>
<b>Max Height:</b> " + data.MaxHeight.ToString("F3") + @"<hr>
<h3>Controls</h3>
<label><input type=""checkbox"" id=""toggleRiver"" checked> Show Rivers</label>
<label><input type=""checkbox"" id=""toggleScatter"" checked> Show Scatter Points</label>
<label><input type=""checkbox"" id=""toggleContour"" checked> Show Contour</label>
<button id=""regen"">Random Seed</button>
<h3>Biome Distribution</h3>
<div id=""stats""></div>
<div id=""legend""></div>
</div>
</div>
<script>
const heightMapData = '" + hsb.ToString() + @"';
const biomeMapData = '" + bsb.ToString() + @"';
const riverMapData = '" + rsb.ToString() + @"';
const scatterData = '" + ssb.ToString() + @"';

const W = " + w + @";
const H = " + h + @";
const SEA_LEVEL = " + data.SeaLevel.ToString("F3", System.Globalization.CultureInfo.InvariantCulture) + @";

const heightMap = heightMapData.split(';').map(r => r.split(',').map(Number));
const biomeMap = biomeMapData.split(';').map(r => r.split(',').map(Number));
const riverMap = riverMapData.split(';').map(r => r.split(',').map(Number));
const scatter = scatterData.split(';').filter(s => s.length > 3).map(s => {
  const p = s.split(',');
  return { x: parseFloat(p[0]), y: parseFloat(p[1]), t: parseInt(p[2]), s: parseFloat(p[3]), r: parseFloat(p[4]) };
});

const biomeColors = {
  0:[20,40,80], 1:[40,90,150], 2:[220,210,160], 3:[120,180,90],
  4:[40,120,60], 5:[130,120,115], 6:[220,225,235], 7:[70,130,80]
};
const biomeNames = ['Deep Water','Shallow','Beach','Grassland','Forest','Rocky','Peak','Valley'];

const canvas = document.getElementById('cw');
const ctx = canvas.getContext('2d');
canvas.width = W; canvas.height = H;

function render() {
  const showRivers = document.getElementById('toggleRiver').checked;
  const showScatter = document.getElementById('toggleScatter').checked;
  const showContour = document.getElementById('toggleContour').checked;
  const img = ctx.createImageData(W, H);
  const d = img.data;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const h = heightMap[y][x];
      const b = biomeMap[y][x];
      const r = riverMap[y][x];
      let c = biomeColors[b];
      const shade = 0.55 + h * 0.65;
      let R = c[0]*shade, G = c[1]*shade, B = c[2]*shade;
      if (showRivers && r > 0.15) {
        const f = Math.min(1, r * 1.3);
        R = R*(1-f*0.6) + 30*f; G = G*(1-f*0.6) + 110*f; B = B*(1-f*0.6) + 200*f;
      }
      const idx = (y*W + x) * 4;
      d[idx] = R|0; d[idx+1] = G|0; d[idx+2] = B|0; d[idx+3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // Contour lines at sea level
  if (showContour) {
    ctx.strokeStyle = 'rgba(255,255,200,0.25)';
    ctx.lineWidth = 0.5;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const hh = heightMap[y][x];
        if ((hh > SEA_LEVEL && heightMap[Math.max(0,y-1)][x] < SEA_LEVEL) ||
            (hh > SEA_LEVEL && y < H-1 && heightMap[y+1][x] < SEA_LEVEL)) {
          ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x+1,y); ctx.stroke();
        }
      }
    }
  }

  if (showScatter) {
    for (const s of scatter) {
      const px = s.x * W, py = s.y * H;
      ctx.save();
      ctx.translate(px, py);
      if (s.t === 0) {
        ctx.fillStyle = '#2d5a2d';
        ctx.beginPath(); ctx.arc(0, 0, 2.2*s.s, 0, 7); ctx.fill();
      } else if (s.t === 1) {
        ctx.fillStyle = '#777';
        ctx.fillRect(-1.5*s.s, -1.5*s.s, 3*s.s, 3*s.s);
      } else if (s.t === 2) {
        ctx.strokeStyle = '#6a8'; ctx.lineWidth = 0.7;
        ctx.beginPath(); ctx.moveTo(0, 2); ctx.lineTo(0, -2); ctx.stroke();
      } else if (s.t === 3) {
        ctx.fillStyle = '#5a7a4a';
        ctx.beginPath(); ctx.arc(0, 0, 1.5, 0, 7); ctx.fill();
      } else {
        ctx.fillStyle = '#aaa'; ctx.fillRect(-1, -1, 2, 2);
      }
      ctx.restore();
    }
  }
}

function showStats() {
  const total = W * H;
  document.getElementById('stats').innerHTML =
    '<div class=""stat-row""><span><span class=""badge b-water""></span>Water</span><span>" + data.WaterCells + " (" + waterPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-beach""></span>Beach</span><span>" + data.BeachCells + " (" + beachPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-grass""></span>Grassland</span><span>" + data.GrassCells + " (" + grassPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-forest""></span>Forest</span><span>" + data.ForestCells + " (" + forestPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-rock""></span>Rocky</span><span>" + data.RockCells + " (" + rockPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-peak""></span>Peaks</span><span>" + data.PeakCells + " (" + peakPct.ToString("F1") + "%)</span></div>' +
    '<div class=""stat-row""><span><span class=""badge b-river""></span>Rivers</span><span>" + data.RiverCells + " cells</span></div>' +
    '<div class=""stat-row""><span>Trees</span><span>" + data.TreeCount + "</span></div>' +
    '<div class=""stat-row""><span>Rocks</span><span>" + data.RockCount + "</span></div>' +
    '<div class=""stat-row""><span>Details</span><span>" + data.DetailCount + "</span></div>';
}

render();
showStats();

document.getElementById('regen').onclick = function() {
  alert('Generate with new seed: run IslandMapGenerator.exe --seed <new_seed>');
};
document.getElementById('toggleRiver').onchange = render;
document.getElementById('toggleScatter').onchange = render;
document.getElementById('toggleContour').onchange = render;
</script>
</body></html>";

            File.WriteAllText(path, html);
        }
    }

    public static class Program
    {
        public static void Main(string[] args)
        {
            int seed = 20261002;
            int w = 256, h = 256;
            float islandRadius = 0.42f;
            float mountains = 0.9f;
            int valleys = 3;
            int rivers = 5;
            float treeDensity = 0.6f;

            for (int i = 0; i < args.Length; i++)
            {
                switch (args[i])
                {
                    case "--seed": seed = int.Parse(args[++i]); break;
                    case "--width": w = int.Parse(args[++i]); break;
                    case "--height": h = int.Parse(args[++i]); break;
                    case "--islandRadius": islandRadius = float.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture); break;
                    case "--mountains": mountains = float.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture); break;
                    case "--valleys": valleys = int.Parse(args[++i]); break;
                    case "--rivers": rivers = int.Parse(args[++i]); break;
                    case "--treeDensity": treeDensity = float.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture); break;
                }
            }

            var cfg = IslandGeneratorCore.IslandConfig.Default(w, h)
            {
                IslandRadius = islandRadius,
                MountainFrequency = mountains,
                ValleyCount = valleys,
                RiverCount = rivers,
                TreeDensity = treeDensity
            };

            Console.WriteLine($"[IslandGenerator] seed={seed} {w}x{h} radius={islandRadius} mountains={mountains} valleys={valleys} rivers={rivers}");

            var t0 = DateTime.UtcNow;
            var island = IslandGeneratorCore.Generate(seed, cfg);
            var elapsed = (DateTime.UtcNow - t0).TotalMilliseconds;

            Console.WriteLine($"[IslandGenerator] Done in {elapsed:F0}ms");
            Console.WriteLine($"  Water: {island.WaterCells}, Beach: {island.BeachCells}, Grass: {island.GrassCells}, Forest: {island.ForestCells}, Rocky: {island.RockCells}, Peaks: {island.PeakCells}");
            Console.WriteLine($"  Rivers: {island.RiverCells} cells | Scatter: {island.Scatter.Count} items (Trees:{island.TreeCount}, Rocks:{island.RockCount}, Detail:{island.DetailCount})");

            string outDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "island_out");
            Directory.CreateDirectory(outDir);

            MapIO.WriteHeightmapPGM(island, Path.Combine(outDir, "island_height.pgm"));
            MapIO.WriteBiomeCSV(island, Path.Combine(outDir, "island_biomes.csv"));
            MapIO.WriteScatterCSV(island, Path.Combine(outDir, "island_scatter.csv"));
            MapIO.WriteReportJson(island, Path.Combine(outDir, "island_report.json"));
            MapIO.WriteHtmlPreview(island, Path.Combine(outDir, "island_preview.html"));

            Console.WriteLine($"[IslandGenerator] Output: {outDir}");
        }
    }
}
