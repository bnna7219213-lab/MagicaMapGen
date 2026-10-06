using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Editor.Scene;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace LowPolyWorldBuilder.Editor.Batch
{
    /// <summary>
    /// Batch-mode importer for mapgen <c>*_map.json</c> deliverables (path B).
    ///
    /// Usage:
    ///   Unity.exe -batchmode -nographics -quit -projectPath &lt;project&gt;
    ///            -executeMethod LowPolyWorldBuilder.Editor.Batch.MapBatchImportEntryPoint.ImportDirectory
    ///            -mapDir &lt;folder containing *_map.json&gt; [-lpwOut &lt;Assets folder&gt;] [-lpwSave]
    ///
    /// Acceptance per map: the instantiated scatter-object count must equal the generator's
    /// own stats.instance_count. That number comes from a separate codebase (Python) and
    /// travels inside the document, so agreeing with it exercises the whole chain --
    /// generator, JSON contract, decoder, scene assembly -- rather than proving the C# is
    /// merely self-consistent.
    ///
    /// Exit codes: 0 = all maps imported and verified; 2 = any failure.
    /// </summary>
    public static class MapBatchImportEntryPoint
    {
        const int ExitOk = 0;
        const int ExitFailed = 2;

        public static void ImportDirectory()
        {
            int exit;
            try { exit = RunBatch(); }
            catch (Exception ex)
            {
                Debug.LogError("[LPW] map import exception: " + ex);
                exit = ExitFailed;
            }
            // In batch mode nobody reads a return value; the exit code is the CI signal.
            if (Application.isBatchMode) EditorApplication.Exit(exit);
        }

        static int RunBatch()
        {
            var args = CommandLineOptions.ArbitraryFromEnvironment();
            args.TryGetValue("mapDir", out string mapDir);
            args.TryGetValue("lpwOut", out string outDir);
            bool saveAssets = args.ContainsKey("lpwSave");
            if (string.IsNullOrEmpty(outDir)) outDir = "Assets/MapImport";

            if (string.IsNullOrEmpty(mapDir) || !Directory.Exists(mapDir))
            {
                Debug.LogError("[LPW] -mapDir <folder> is required and must exist; got: " + mapDir);
                return ExitFailed;
            }

            var files = Directory.GetFiles(mapDir, "*_map.json", SearchOption.TopDirectoryOnly)
                               .OrderBy(f => f, StringComparer.Ordinal).ToList();
            if (files.Count == 0)
            {
                Debug.LogError("[LPW] no *_map.json files in " + mapDir);
                return ExitFailed;
            }

            Debug.Log("[LPW] importing " + files.Count + " map document(s) from " + mapDir);
            var failures = new List<string>();
            int verified = 0;

            foreach (var file in files)
            {
                string label = Path.GetFileNameWithoutExtension(file);
                var timer = Stopwatch.StartNew();
                GameObject root = null;
                try
                {
                    var doc = MapDocument.Load(file);
                    var report = new WorldBuildReport
                    {
                        seed = doc.Seed,
                        generatorVersion = doc.GeneratorVersion,
                        profileName = label,
                        theme = doc.ThemeId,
                        gridWidth = doc.Width,
                        gridHeight = doc.Height,
                        timestampUtc = DateTime.UtcNow,
                    };

                    EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                    root = new SceneAssembler().FromJson(doc, label, report);
                    timer.Stop();
                    report.buildDurationMilliseconds = timer.ElapsedMilliseconds;

                    var problems = Verify(doc, root, out int sceneObjects, out int stated);
                    if (problems.Count > 0)
                    {
                        failures.Add(label + ": " + string.Join("; ", problems));
                        Debug.LogError("[LPW] " + label + " FAILED: " + string.Join("; ", problems));
                    }
                    else
                    {
                        verified++;
                        Debug.Log("[LPW] " + label + " OK theme=" + doc.ThemeId
                                  + " grid=" + doc.Width + "x" + doc.Height
                                  + " instances=" + sceneObjects + " (== stats.instance_count=" + stated + ")"
                                  + " height=" + doc.HeightSource
                                  + " contract=" + doc.ContractSummary
                                  + " ms=" + report.buildDurationMilliseconds);
                    }

                    if (saveAssets)
                    {
                        PrefabAssetWriter.EnsureFolder(outDir);
                        PrefabAssetWriter.SaveRootAsPrefab(root, outDir, label);
                        PrefabAssetWriter.SaveScene(outDir, label);
                        PrefabAssetWriter.WriteReport(report, outDir, label);
                    }
                }
                catch (Exception ex)
                {
                    timer.Stop();
                    failures.Add(label + ": " + ex.GetType().Name + ": " + ex.Message);
                    Debug.LogError("[LPW] " + label + " threw: " + ex);
                }
                finally
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    if (root != null) UnityEngine.Object.DestroyImmediate(root);
                    EditorUtility.UnloadUnusedAssetsImmediate();
                    GC.Collect();
                }
            }

            if (saveAssets) AssetDatabase.SaveAssets();
            Debug.Log("[LPW] map import summary: " + verified + "/" + files.Count
                      + " verified, " + failures.Count + " failure(s)");
            foreach (var f in failures) Debug.LogError("[LPW]   " + f);
            return failures.Count == 0 ? ExitOk : ExitFailed;
        }

        /// <summary>Acceptance check. Empty means pass; else one message per problem.</summary>
        static List<string> Verify(MapDocument doc, GameObject root, out int sceneObjects, out int stated)
        {
            var problems = new List<string>();
            sceneObjects = -1;
            stated = doc.StatedInstanceCount;

            // FromJson renames the map root, so locate Scatter by walking rather than by
            // a hard-coded path.
            Transform scatter = null;
            foreach (Transform child in root.transform)
            {
                foreach (Transform grand in child)
                    if (grand.name == "Scatter") { scatter = grand; break; }
                if (scatter != null) break;
            }

            if (scatter == null)
            {
                problems.Add("no Scatter container under the imported root; hierarchy was: "
                             + Describe(root.transform, 0));
            }
            else
            {
                sceneObjects = scatter.childCount;
                if (stated < 0)
                    problems.Add("map.json carries no stats.instance_count to verify against");
                else if (sceneObjects != stated)
                    problems.Add("scene has " + sceneObjects + " instance objects but stats.instance_count says "
                                 + stated);
            }

            bool hasTerrain = false;
            foreach (var mf in root.GetComponentsInChildren<MeshFilter>(true))
                if (mf.name == "Terrain") { hasTerrain = true; break; }
            if (!hasTerrain) problems.Add("no Terrain mesh was generated");

            return problems;
        }

        /// <summary>Compact hierarchy dump, so a failed import says what it actually built.</summary>
        static string Describe(Transform t, int depth)
        {
            var sb = new System.Text.StringBuilder();
            sb.Append(t.name).Append('(').Append(t.childCount).Append(')');
            for (int i = 0; i < t.childCount && depth < 4; i++)
            {
                sb.Append(" [").Append(Describe(t.GetChild(i), depth + 1)).Append(']');
            }
            return sb.ToString();
        }
    }
}
