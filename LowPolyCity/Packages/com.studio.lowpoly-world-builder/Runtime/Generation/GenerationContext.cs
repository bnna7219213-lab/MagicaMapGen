using System;
using LowPolyWorldBuilder.Data;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Carries seed, region key, random stream, report and budget through the
    /// generator pipeline. Generators never touch UnityEngine.Random.
    /// </summary>
    public sealed class GenerationContext
    {
        public int Seed { get; }
        public string RegionKey { get; }
        public WorldBuildReport Report { get; }
        public DeterministicRandom Random { get; }
        public int objectBudget = 20000;

        public GenerationContext(int seed, string regionKey, WorldBuildReport report)
        {
            Seed = seed;
            RegionKey = regionKey ?? "world";
            Report = report ?? new WorldBuildReport();
            Random = new DeterministicRandom(HashSeed(seed, RegionKey));
        }

        public GenerationContext SubContext(string subKey)
        {
            var ctx = new GenerationContext(Seed, RegionKey + "/" + subKey, Report);
            ctx.objectBudget = objectBudget;
            return ctx;
        }

        public static int HashSeed(int seed, string key)
        {
            unchecked
            {
                uint h = (uint)seed;
                foreach (char c in key) { h ^= c; h *= 16777619u; }
                return (int)h;
            }
        }
    }
}
