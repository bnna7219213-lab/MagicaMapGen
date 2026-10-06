using System;
using System.Collections.Generic;
using System.Text;

namespace LowPolyWorldBuilder.Data
{
    public enum ReportLevel { Info, Warning, Error }

    [Serializable]
    public sealed class ReportEntry
    {
        public ReportLevel level;
        public string stage;
        public string message;
    }

    [Serializable]
    public sealed class BuildingArchetypeCount
    {
        public string archetype;
        public int count;
    }

    /// <summary>
    /// Generation report: seed, generator version, asset references, stats and
    /// validation output (plan 3.1 item 7). Serialized to JSON by the batch
    /// entry point.
    /// </summary>
    [Serializable]
    public sealed class WorldBuildReport
    {
        public int seed;
        public string generatorVersion = "0.3.0";
        public string profileName;
        public string theme;
        public int gridWidth;
        public int gridHeight;
        public long buildDurationMilliseconds;
        public DateTime timestampUtc;
        public List<ReportEntry> entries = new List<ReportEntry>();
        public List<BuildingArchetypeCount> buildingArchetypes = new List<BuildingArchetypeCount>();

        [NonSerialized] public int roadSegmentCount;
        [NonSerialized] public int blockCount;
        [NonSerialized] public int lotCount;
        [NonSerialized] public int buildingCount;
        [NonSerialized] public int scatterCount;
        [NonSerialized] public int prefabInstanceCount;
        [NonSerialized] public readonly List<string> assetReferences = new List<string>();

        public void Info(string stage, string msg) => Add(ReportLevel.Info, stage, msg);
        public void Warn(string stage, string msg) => Add(ReportLevel.Warning, stage, msg);
        public void Error(string stage, string msg) => Add(ReportLevel.Error, stage, msg);

        void Add(ReportLevel l, string stage, string msg)
            => entries.Add(new ReportEntry { level = l, stage = stage, message = msg });

        public bool HasErrors
        {
            get
            {
                foreach (var e in entries) if (e.level == ReportLevel.Error) return true;
                return false;
            }
        }

        public string ToSummaryText()
        {
            var sb = new StringBuilder();
            sb.AppendLine($"WorldBuildReport seed={seed} version={generatorVersion} time={timestampUtc:u}");
            sb.AppendLine($"theme={theme} grid={gridWidth}x{gridHeight} buildMs={buildDurationMilliseconds}");
            sb.AppendLine($"roads={roadSegmentCount} blocks={blockCount} lots={lotCount} buildings={buildingCount} scatter={scatterCount} prefabs={prefabInstanceCount}");
            if (buildingArchetypes != null && buildingArchetypes.Count > 0)
            {
                var archetypes = new List<string>();
                foreach (var item in buildingArchetypes)
                    archetypes.Add(item.archetype + ":" + item.count);
                sb.AppendLine("architecture=" + string.Join(", ", archetypes));
            }
            foreach (var e in entries)
                sb.AppendLine($"[{e.level}] ({e.stage}) {e.message}");
            return sb.ToString();
        }
    }
}
