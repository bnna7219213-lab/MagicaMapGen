using System;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Deterministic random stream. Same seed => same sequence on every
    /// machine (xorshift128+, platform independent).
    /// </summary>
    public sealed class DeterministicRandom
    {
        ulong _s0, _s1;

        public DeterministicRandom(int seed)
        {
            // SplitMix64 to expand the 32-bit seed
            ulong z = (ulong)seed + 0x9E3779B97F4A7C15ul;
            _s0 = Mix(ref z);
            _s1 = Mix(ref z);
            if (_s0 == 0 && _s1 == 0) _s1 = 1;
        }

        static ulong Mix(ref ulong z)
        {
            z = (z + 0x9E3779B97F4A7C15ul);
            ulong x = z;
            x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ul;
            x = (x ^ (x >> 27)) * 0x94D049BB133111EBul;
            return x ^ (x >> 31);
        }

        ulong NextUlong()
        {
            ulong s1 = _s0;
            ulong s0 = _s1;
            _s0 = s0;
            s1 ^= s1 << 23;
            _s1 = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
            return _s1 + s0;
        }

        public int NextInt(int minInclusive, int maxExclusive)
        {
            if (maxExclusive <= minInclusive) return minInclusive;
            ulong span = (ulong)(maxExclusive - minInclusive);
            return minInclusive + (int)(NextUlong() % span);
        }

        public float NextFloat(float min, float max)
        {
            float t = (float)(NextUlong() >> 11) * (1f / 9007199254740992f);
            return min + (max - min) * t;
        }

        public bool Chance(float p) => NextFloat(0f, 1f) < p;

        /// <summary>Weighted pick. Returns index, or -1 if all weights <= 0.</summary>
        public int WeightedPick(float[] weights)
        {
            float total = 0f;
            foreach (var w in weights) if (w > 0) total += w;
            if (total <= 0f) return -1;
            float r = NextFloat(0f, total);
            for (int i = 0; i < weights.Length; i++)
            {
                if (weights[i] <= 0) continue;
                r -= weights[i];
                if (r <= 0f) return i;
            }
            return weights.Length - 1;
        }
    }
}
