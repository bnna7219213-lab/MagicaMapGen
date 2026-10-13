using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Drives <c>python -m mapgen --overlay</c> from the editor: writes the differ's
    /// edits.json next to the base map, runs the CLI, and points back at the newly
    /// produced map.json so the scene can be reloaded. This closes the Unity half of
    /// the phase-3 loop (the generator stays the source of truth; Unity only emits ops).
    /// </summary>
    public static class OverlayReceiver
    {
        public struct Result
        {
            public int ExitCode;
            public string MapJsonPath;
            public string Output;
            public bool Success => ExitCode == 0 && File.Exists(MapJsonPath);
        }

        /// <summary>Python interpreter to use: explicit path, then MAPGEN_PYTHON, then "python".</summary>
        public static string ResolvePython(string explicitPath = null)
        {
            if (!string.IsNullOrEmpty(explicitPath)) return explicitPath;
            var env = Environment.GetEnvironmentVariable("MAPGEN_PYTHON");
            return string.IsNullOrEmpty(env) ? "python" : env;
        }

        public static Result Run(string repoRoot, string baseMapJson, string editsJson,
                                 string outDir, string label, string python = null)
        {
            var args = new StringBuilder()
                .Append("-m mapgen --overlay \"").Append(baseMapJson).Append("\"")
                .Append(" --edits \"").Append(editsJson).Append("\"")
                .Append(" --out \"").Append(outDir).Append("\"")
                .Append(" --label \"").Append(label).Append("\" --format map --validate")
                .ToString();

            var psi = new ProcessStartInfo(ResolvePython(python), args)
            {
                WorkingDirectory = repoRoot,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            var sb = new StringBuilder();
            int exit;
            using (var proc = Process.Start(psi))
            {
                sb.Append(proc.StandardOutput.ReadToEnd());
                sb.Append(proc.StandardError.ReadToEnd());
                proc.WaitForExit();
                exit = proc.ExitCode;
            }
            return new Result
            {
                ExitCode = exit,
                MapJsonPath = Path.Combine(outDir, label + "_map.json"),
                Output = sb.ToString(),
            };
        }
    }
}
