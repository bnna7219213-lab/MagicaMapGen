using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>One entry of grid.biome_legend.</summary>
    public sealed class MapBiome
    {
        public int Id;
        public string Key = "";
        public string Name = "";
        /// <summary>0xRRGGBB</summary>
        public uint ColorRgb;
        public bool IsWater;
        public bool Walkable;
        public bool Buildable;
        public double MovementCost;
    }

    /// <summary>One placed object from map.json's instances array.</summary>
    public sealed class MapInstance
    {
        public int Id;
        public string Category = "";
        public string Type = "";
        public int X, Y;
        /// <summary>[world_x, world_y, world_z] in metres.</summary>
        public double[] World = new double[3];
        public double RotationDegrees;
        public double Scale = 1.0;
        public string Biome = "";
        public double Slope;
        public double WaterDepth;
        public string Region = "";
        public int Cluster = -1;
    }

    /// <summary>A river polyline in grid cells.</summary>
    public sealed class MapRiver
    {
        public int Id;
        public int Length;
        public bool ReachedWater;
        public List<int[]> Path = new List<int[]>();
    }

    /// <summary>
    /// Faithful in-memory model of a mapgen <c>*_map.json</c> (artifact schema v2).
    ///
    /// Deliberately NOT mapped onto BuildPlan: that model is road-graph / city-block
    /// shaped, and map.json contains no roads, blocks or lots. Forcing a tilemap into
    /// it would mean inventing roads the generator never produced, so the decoder keeps
    /// its own shape and SceneAssembler.FromJson consumes it directly.
    ///
    /// All grids are row-major with index = y * width + x, matching the document's
    /// declared scan_order.
    /// </summary>
    public sealed class MapDocument
    {
        public const int MinSupportedSchema = 1;
        public const int MaxKnownSchema = 2;

        public int SchemaVersion;
        public string GeneratorVersion = "";
        public string Label = "";
        public int Seed;
        public string ThemeId = "";
        public string ThemeDisplayName = "";
        public bool ContractPassed;
        public string ContractSummary = "";

        public int Width, Height;
        public double TileSizeMeters = 8.0;
        public double HeightScaleMeters = 120.0;
        public double SeaLevelNorm;
        public string HeightmapRawUrl = "";

        public int[] BiomeGrid = Array.Empty<int>();
        public float[] HeightGrid = Array.Empty<float>();
        public float[] MoistureGrid = Array.Empty<float>();
        public float[] RiverGrid = Array.Empty<float>();

        public List<MapBiome> Legend = new List<MapBiome>();
        readonly Dictionary<int, MapBiome> _legendById = new Dictionary<int, MapBiome>();
        public List<MapInstance> Instances = new List<MapInstance>();
        public List<MapRiver> Rivers = new List<MapRiver>();
        public Dictionary<string, double> Stats = new Dictionary<string, double>(StringComparer.Ordinal);

        /// <summary>Non-fatal notes: unknown newer schema, absent optional grids, missing sidecar.</summary>
        public List<string> Warnings = new List<string>();

        public int CellCount => Width * Height;
        public MapBiome BiomeById(int id) => _legendById.TryGetValue(id, out var b) ? b : null;

        /// <summary>Which source the meshing heights came from (the 16-bit PGM when present).</summary>
        public string HeightSource { get; private set; } = "height_rle";

        public static MapDocument Load(string path)
        {
            if (string.IsNullOrEmpty(path)) throw new MapDecodeException("", "map path is empty");
            if (!File.Exists(path)) throw new MapDecodeException("", $"map.json not found: {path}");
            return Decode(File.ReadAllText(path), Path.GetDirectoryName(path));
        }

        public static MapDocument Decode(string json, string baseDirectory = null)
        {
            var root = MiniJson.Parse(json) as Dictionary<string, object>
                       ?? throw new MapDecodeException("", "top-level value is not a JSON object");
            var doc = new MapDocument();
            doc.SchemaVersion = Json.AsInt(root, "schema_version", 0);
            if (doc.SchemaVersion < MinSupportedSchema)
                throw new MapDecodeException("schema_version",
                    $"unsupported schema_version {doc.SchemaVersion} (minimum {MinSupportedSchema})");
            if (doc.SchemaVersion > MaxKnownSchema)
                doc.Warnings.Add($"schema_version {doc.SchemaVersion} is newer than the known maximum "
                                 + $"{MaxKnownSchema}; decoding what is recognised and ignoring the rest");

            doc.GeneratorVersion = Json.AsString(root, "generator_version", "");
            doc.Label = Json.AsString(root, "label", "");
            doc.Seed = Json.AsInt(root, "seed", 0);

            var theme = Json.AsObject(root, "theme");
            doc.ThemeId = Json.AsString(theme, "id", "");
            doc.ThemeDisplayName = Json.AsString(theme, "display_name", "");

            var contract = Json.AsObject(root, "contract");
            doc.ContractPassed = Json.AsBool(contract, "passed", false);
            doc.ContractSummary = doc.ContractPassed ? "passed" : "FAILED";

            var grid = Json.AsObject(root, "grid");
            doc.Width = Json.AsInt(grid, "width", 0);
            doc.Height = Json.AsInt(grid, "height", 0);
            if (doc.Width < 1 || doc.Height < 1)
                throw new MapDecodeException("grid", $"width/height must be >= 1, got {doc.Width}x{doc.Height}");
            doc.TileSizeMeters = Json.AsNumber(grid, "tile_size_meters", 8.0);
            doc.HeightScaleMeters = Json.AsNumber(grid, "height_scale_meters", 120.0);

            foreach (var raw in Json.AsList(grid, "biome_legend"))
            {
                var entry = Json.Obj(raw, "grid.biome_legend[]");
                var b = new MapBiome
                {
                    Id = Json.AsInt(entry, "id", -1),
                    Key = Json.AsString(entry, "key", ""),
                    Name = Json.AsString(entry, "name", ""),
                    ColorRgb = ParseHexColor(Json.AsString(entry, "color_hex", "#000000")),
                    IsWater = Json.AsBool(entry, "is_water", false),
                    Walkable = Json.AsBool(entry, "walkable", false),
                    Buildable = Json.AsBool(entry, "buildable", false),
                    MovementCost = Json.AsNumber(entry, "movement_cost", 1.0),
                };
                if (b.Id < 0)
                    throw new MapDecodeException("grid.biome_legend", "legend entry has no valid id");
                doc.Legend.Add(b);
                doc._legendById[b.Id] = b;
            }
            if (doc.Legend.Count == 0)
                throw new MapDecodeException("grid.biome_legend",
                    "biome legend is empty; biome_rle cannot be interpreted");

            doc.BiomeGrid = DecodeRle(json, grid, "biome_rle", doc.Width, doc.Height);
            doc.HeightGrid = DecodeNormalisedRle(json, grid, "height_rle", doc.Width, doc.Height, 255.0);
            doc.RiverGrid = DecodeNormalisedRle(json, grid, "river_rle", doc.Width, doc.Height, 255.0);

            // v2 addition: per-cell humidity, for triplanar blending / foliage tinting.
            if (grid.ContainsKey("moisture_rle"))
                doc.MoistureGrid = DecodeNormalisedRle(json, grid, "moisture_rle", doc.Width, doc.Height, 255.0);
            else
                doc.Warnings.Add("grid.moisture_rle absent (schema v1 document); humidity unavailable");

            // v2 addition: lossless 16-bit heightmap sidecar.
            doc.HeightmapRawUrl = Json.AsString(grid, "heightmap_raw_url", "");
            if (!string.IsNullOrEmpty(doc.HeightmapRawUrl))
            {
                if (Path.IsPathRooted(doc.HeightmapRawUrl)
                    || doc.HeightmapRawUrl.IndexOf('/') >= 0
                    || doc.HeightmapRawUrl.IndexOf('\\') >= 0)
                    throw new MapDecodeException("grid.heightmap_raw_url",
                        $"must be a bare relative filename, got '{doc.HeightmapRawUrl}'");
                if (baseDirectory != null)
                {
                    string sidecar = Path.Combine(baseDirectory, doc.HeightmapRawUrl);
                    if (File.Exists(sidecar))
                    {
                        doc.HeightGrid = ReadHeightPgm(sidecar, doc.Width, doc.Height);
                        doc.HeightSource = doc.HeightmapRawUrl;
                    }
                    else
                    {
                        doc.Warnings.Add($"heightmap sidecar '{doc.HeightmapRawUrl}' is missing next to map.json; "
                                         + "fell back to 8-bit height_rle");
                    }
                }
            }

            var features = Json.AsObject(root, "features");
            doc.SeaLevelNorm = Json.AsNumber(features, "sea_level", 0.0);
            foreach (var raw in Json.AsList(features, "rivers"))
            {
                var entry = Json.Obj(raw, "features.rivers[]");
                var r = new MapRiver
                {
                    Id = Json.AsInt(entry, "id", -1),
                    Length = Json.AsInt(entry, "length", 0),
                    ReachedWater = Json.AsBool(entry, "reached_water", false),
                };
                foreach (var pt in Json.AsList(entry, "path"))
                {
                    var pair = Json.AsList(pt);
                    if (pair.Count < 2)
                        throw new MapDecodeException("features.rivers[].path", "expected [x, y]");
                    r.Path.Add(new[]
                    {
                        (int)Json.ToNumber(pair[0], "river path x"),
                        (int)Json.ToNumber(pair[1], "river path y"),
                    });
                }
                doc.Rivers.Add(r);
            }

            foreach (var raw in Json.AsList(root, "instances"))
            {
                var entry = Json.Obj(raw, "instances[]");
                var inst = new MapInstance
                {
                    Id = Json.AsInt(entry, "id", -1),
                    Category = Json.AsString(entry, "cat", ""),
                    Type = Json.AsString(entry, "type", ""),
                    X = Json.AsInt(entry, "x", -1),
                    Y = Json.AsInt(entry, "y", -1),
                    RotationDegrees = Json.AsNumber(entry, "rot", 0.0),
                    Scale = Json.AsNumber(entry, "scale", 1.0),
                    Biome = Json.AsString(entry, "biome", ""),
                    Slope = Json.AsNumber(entry, "slope", 0.0),
                    WaterDepth = Json.AsNumber(entry, "water_depth", 0.0),
                    Region = Json.AsString(entry, "region", ""),
                    Cluster = Json.AsInt(entry, "cluster", -1),
                };
                if (inst.X < 0 || inst.Y < 0 || inst.X >= doc.Width || inst.Y >= doc.Height)
                    throw new MapDecodeException("instances",
                        $"instance {inst.Id} at ({inst.X},{inst.Y}) is outside the {doc.Width}x{doc.Height} grid");
                var world = Json.AsList(entry, "world");
                if (world.Count < 3)
                    throw new MapDecodeException($"instances[{inst.Id}].world", "expected 3 numbers");
                for (int k = 0; k < 3; k++)
                    inst.World[k] = Json.ToNumber(world[k], $"instances[{inst.Id}].world");
                doc.Instances.Add(inst);
            }

            var stats = Json.AsObject(root, "stats");
            foreach (var kv in stats)
                if (kv.Value is double d) doc.Stats[kv.Key] = d;

            Validate(doc);
            return doc;
        }

        /// <summary>Cross-field checks that a JSON Schema cannot express.</summary>
        static void Validate(MapDocument doc)
        {
            foreach (var id in new HashSet<int>(doc.BiomeGrid))
                if (doc.BiomeById(id) == null)
                    throw new MapDecodeException("grid.biome_rle",
                        $"biome id {id} appears in the grid but is not declared in biome_legend");
            if (doc.Stats.TryGetValue("instance_count", out double stated)
                && (int)stated != doc.Instances.Count)
                throw new MapDecodeException("stats.instance_count",
                    $"stats claims {stated} instances but the array holds {doc.Instances.Count}");
        }

        /// <summary>Instance count as stated by the generator, or -1 when absent.</summary>
        public int StatedInstanceCount => Stats.TryGetValue("instance_count", out double d) ? (int)d : -1;

        public float HeightAt(int x, int y) => HeightGrid[y * Width + x];
        public int BiomeAt(int x, int y) => BiomeGrid[y * Width + x];
        public float MoistureAt(int x, int y) =>
            MoistureGrid.Length == CellCount ? MoistureGrid[y * Width + x] : 0f;

        public float WorldY(float heightNorm) => (float)(heightNorm * HeightScaleMeters);
        public float CellToWorldX(int x) => (float)((x + 0.5) * TileSizeMeters);
        public float CellToWorldZ(int y) => (float)((y + 0.5) * TileSizeMeters);

        // ---- internals -------------------------------------------------------

        static int[] DecodeRle(string json, Dictionary<string, object> grid, string key,
                               int width, int height)
        {
            int total = width * height;
            var flat = new int[total];
            int at = 0;
            foreach (var run in Json.AsList(json, grid, key))
            {
                var pair = Json.AsList(run);
                if (pair.Count < 2)
                    throw new MapDecodeException($"grid.{key}", "each run must be [value, length]");                int value = (int)Json.ToNumber(pair[0], $"grid.{key} value");
                int length = (int)Json.ToNumber(pair[1], $"grid.{key} run length");
                if (length < 0)
                    throw new MapDecodeException($"grid.{key}", $"negative run length {length}");
                if (at + length > total)
                    throw new MapDecodeException($"grid.{key}",
                        "runs decode to more than width*height cells");
                for (int k = 0; k < length; k++) flat[at++] = value;
            }
            if (at != total)
                throw new MapDecodeException($"grid.{key}",
                    $"runs decode to {at} cells, expected width*height = {total}");
            return flat;
        }

        static float[] DecodeNormalisedRle(string json, Dictionary<string, object> grid, string key,
                                           int width, int height, double scale)
        {
            var raw = DecodeRle(json, grid, key, width, height);
            var result = new float[raw.Length];
            for (int i = 0; i < raw.Length; i++) result[i] = (float)(raw[i] / scale);
            return result;
        }

        /// <summary>Read a 16-bit binary PGM (P5, maxval 65535) height field.</summary>
        static float[] ReadHeightPgm(string path, int width, int height)
        {
            byte[] blob = File.ReadAllBytes(path);
            int i = 0;

            string Token()
            {
                while (i < blob.Length)
                {
                    if (blob[i] == '#') { while (i < blob.Length && blob[i] != '\n') i++; }
                    else if (char.IsWhiteSpace((char)blob[i])) i++;
                    else break;
                }
                int start = i;
                while (i < blob.Length && !char.IsWhiteSpace((char)blob[i])) i++;
                return System.Text.Encoding.ASCII.GetString(blob, start, i - start);
            }

            if (Token() != "P5")
                throw new MapDecodeException("heightmap_raw_url", "sidecar is not a binary PGM (expected P5)");
            int w = int.Parse(Token(), CultureInfo.InvariantCulture);
            int h = int.Parse(Token(), CultureInfo.InvariantCulture);
            int maxval = int.Parse(Token(), CultureInfo.InvariantCulture);
            if (maxval != 65535)
                throw new MapDecodeException("heightmap_raw_url",
                    $"expected maxval 65535 for a lossless heightmap, got {maxval}");
            if (w != width || h != height)
                throw new MapDecodeException("heightmap_raw_url",
                    $"sidecar is {w}x{h} but map.json grid is {width}x{height}");
            i++; // the single whitespace byte after maxval

            long expected = (long)w * h * 2;
            if (blob.Length - i < expected)
                throw new MapDecodeException("heightmap_raw_url",
                    $"truncated PGM payload: got {blob.Length - i} bytes, expected {expected}");

            var result = new float[w * h];
            for (int p = 0; p < w * h; p++)
            {
                int v = blob[i] | (blob[i + 1] << 8); // little-endian, matching the generator's writer
                i += 2;
                result[p] = v / 65535f;
            }
            return result;
        }

        static uint ParseHexColor(string hex)
        {
            if (string.IsNullOrEmpty(hex)) return 0x000000;
            string s = hex.TrimStart('#');
            if (s.Length != 6) return 0x000000;
            return uint.Parse(s, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        }
    }

    /// <summary>Typed, path-qualified accessors over MiniJson output. Every mismatch throws.</summary>
    static class Json
    {
        /// <summary>Narrow a list element to a JSON object, reporting the owning path on failure.</summary>
        public static Dictionary<string, object> Obj(object src, string path)
        {
            if (src is Dictionary<string, object> o) return o;
            throw new MapDecodeException(path,
                $"expected a JSON object, got {(src == null ? "null" : src.GetType().Name)}");
        }

        public static Dictionary<string, object> AsObject(Dictionary<string, object> src, string key)
        {
            if (src != null && src.TryGetValue(key, out var v) && v is Dictionary<string, object> o) return o;
            return new Dictionary<string, object>();
        }

        public static List<object> AsList(Dictionary<string, object> src, string key)
        {
            if (src != null && src.TryGetValue(key, out var v) && v is List<object> l) return l;
            return new List<object>();
        }

        /// <summary>Array accessor that reports the owning key when the value is the wrong shape.</summary>
        public static List<object> AsList(string ownerPath, Dictionary<string, object> src, string key)
        {
            if (src != null && src.TryGetValue(key, out var v))
            {
                if (v is List<object> l) return l;
                throw new MapDecodeException(Join(ownerPath, key),
                    $"expected an array, got {(v == null ? "null" : v.GetType().Name)}");
            }
            return new List<object>();
        }

        public static List<object> AsList(object src)
        {
            if (src is List<object> l) return l;
            throw new MapDecodeException("",
                $"expected a JSON array, got {(src == null ? "null" : src.GetType().Name)}");
        }

        public static string AsString(Dictionary<string, object> src, string key, string fallback)
        {
            if (src != null && src.TryGetValue(key, out var v))
            {
                if (v is string s) return s;
                if (v == null) return fallback;
                throw new MapDecodeException(key, $"expected a string, got {v.GetType().Name}");
            }
            return fallback;
        }

        public static bool AsBool(Dictionary<string, object> src, string key, bool fallback)
        {
            if (src != null && src.TryGetValue(key, out var v))
            {
                if (v is bool b) return b;
                if (v == null) return fallback;
                throw new MapDecodeException(key, $"expected a boolean, got {v.GetType().Name}");
            }
            return fallback;
        }

        public static int AsInt(Dictionary<string, object> src, string key, int fallback)
        {
            double d = AsNumber(src, key, fallback);
            if (Math.Abs(d - Math.Round(d)) > 1e-9)
                throw new MapDecodeException(key, $"expected an integer, got {d}");
            return (int)Math.Round(d);
        }

        public static double AsNumber(Dictionary<string, object> src, string key, double fallback)
        {
            if (src != null && src.TryGetValue(key, out var v))
            {
                if (v is double d) return d;
                if (v == null) return fallback;
                throw new MapDecodeException(key, $"expected a number, got {v.GetType().Name}");
            }
            return fallback;
        }

        public static double ToNumber(object v, string path)
        {
            if (v is double d) return d;
            if (v is bool b) return b ? 1 : 0;
            throw new MapDecodeException(path,
                $"expected a number, got {(v == null ? "null" : v.GetType().Name)}");
        }

        static string Join(string owner, string key) => string.IsNullOrEmpty(owner) ? key : $"{owner}.{key}";
    }
}
