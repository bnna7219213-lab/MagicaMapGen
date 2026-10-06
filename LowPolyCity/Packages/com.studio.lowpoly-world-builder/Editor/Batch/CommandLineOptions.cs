using System;
using System.Collections.Generic;

namespace LowPolyWorldBuilder.Editor.Batch
{
    /// <summary>
    /// Parses -executeMethod-adjacent command line args:
    ///   -lpwProfile <asset path to WorldBuildProfile>
    ///   -lpwOut <output folder under Assets>
    ///   -lpwSeed <int override>
    /// </summary>
    public sealed class CommandLineOptions
    {
        public string ProfilePath;
        public string OutputFolder;
        public int? SeedOverride;

        public static CommandLineOptions Parse(string[] args)
        {
            var o = new CommandLineOptions();
            for (int i = 0; i < args.Length - 1; i++)
            {
                switch (args[i])
                {
                    case "-lpwProfile": o.ProfilePath = args[i + 1]; break;
                    case "-lpwOut": o.OutputFolder = args[i + 1]; break;
                    case "-lpwSeed":
                        if (int.TryParse(args[i + 1], out int s)) o.SeedOverride = s;
                        break;
                }
            }
            return o;
        }

        public static CommandLineOptions FromEnvironment()
            => Parse(Environment.GetCommandLineArgs());

        /// <summary>
        /// Generic <c>-key value</c> collector for entry points that take their own
        /// switches (e.g. the map importer's -mapDir / -lpwOut). Switches given without
        /// a following value are recorded with an empty string so a bare flag can be
        /// tested for presence.
        /// </summary>
        public static Dictionary<string, string> ParseArbitrary(string[] args)
        {
            var map = new Dictionary<string, string>(StringComparer.Ordinal);
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (!a.StartsWith("-", StringComparison.Ordinal)) continue;
                string key = a.TrimStart('-');
                if (key.Length == 0) continue;
                bool hasValue = i + 1 < args.Length && !args[i + 1].StartsWith("-", StringComparison.Ordinal);
                map[key] = hasValue ? args[i + 1] : string.Empty;
                if (hasValue) i++;
            }
            return map;
        }

        public static Dictionary<string, string> ArbitraryFromEnvironment()
            => ParseArbitrary(Environment.GetCommandLineArgs());
    }
}
