using System;
using System.Collections.Generic;
using System.IO;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Editor.Scene;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace LowPolyWorldBuilder.Editor.Batch
{
    /// <summary>
    /// Headless proof of the phase-3 edit round-trip.
    ///
    ///   Unity.exe -batchmode -nographics -quit -projectPath &lt;project&gt;
    ///     -executeMethod LowPolyWorldBuilder.Editor.Batch.MapEditRoundTripEntryPoint.Verify
    ///     -roundtripBase &lt;abs path to a *_map.json&gt;
    ///     -roundtripRepo &lt;abs path to the repo root holding mapgen/&gt;
    ///     -roundtripWork &lt;abs output folder&gt;
    ///   (env MAPGEN_PYTHON points the overlay at the same interpreter as the harness)
    ///
    /// Builds a scene from the base, mutates tagged objects (delete one, move one,
    /// hand-add one), runs SceneDiffer to emit edits.json, runs mapgen --overlay, then
    /// reloads the produced map.json and checks the edits landed with v4 provenance.
    /// Exits 0 only if the whole loop closes; 2 otherwise.
    /// </summary>
    public static class MapEditRoundTripEntryPoint
    {
        const int ExitOk = 0;
        const int ExitFailed = 2;

        public static void Verify()
        {
            int exit;
            try { exit = Run(); }
            catch (Exception ex)
            {
                Debug.LogError("[LPW] round-trip exception: " + ex);
                exit = ExitFailed;
            }
            if (Application.isBatchMode) EditorApplication.Exit(exit);
        }

        static int Run()
        {
            var args = CommandLineOptions.ArbitraryFromEnvironment();
            args.TryGetValue("roundtripBase", out string baseMap);
            args.TryGetValue("roundtripRepo", out string repoRoot);
            args.TryGetValue("roundtripWork", out string workDir);
            var failures = new List<string>();

            if (string.IsNullOrEmpty(baseMap) || !File.Exists(baseMap))
            { Debug.LogError("[LPW] -roundtripBase must point to an existing map.json"); return ExitFailed; }
            if (string.IsNullOrEmpty(repoRoot) || !Directory.Exists(repoRoot))
            { Debug.LogError("[LPW] -roundtripRepo must be the repo root"); return ExitFailed; }
            if (string.IsNullOrEmpty(workDir)) workDir = Path.GetDirectoryName(baseMap);
            Directory.CreateDirectory(workDir);

            var doc = MapDocument.Load(baseMap);
            if (doc.Instances.Count < 3)
            { Debug.LogError("[LPW] base needs >= 3 instances to exercise the loop"); return ExitFailed; }
            double tile = doc.TileSizeMeters;
            int baseCount = doc.Instances.Count;

            EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            var report = new WorldBuildReport { seed = doc.Seed, theme = doc.ThemeId,
                                                profileName = "roundtrip", gridWidth = doc.Width,
                                                gridHeight = doc.Height };
            GameObject root = new SceneAssembler().FromJson(doc, "roundtrip", report);
            try
            {
                var tags = new List<MapInstanceId>(root.GetComponentsInChildren<MapInstanceId>(true));
                var byId = new Dictionary<int, MapInstanceId>();
                foreach (var t in tags) byId[t.Id] = t;

                // Pick two cells that hold no existing instance, so the move/add do not
                // trip mapgen's collision-drop (which would silently delete an auto
                // object and make the expected instance count ambiguous).
                var occupied = new HashSet<long>();
                foreach (var i in doc.Instances) occupied.Add(((long)i.X << 32) | (uint)i.Y);
                int FreeX = -1, FreeY = -1;
                Func<bool> takeFree = null;
                takeFree = () =>
                {
                    for (int yy = 1; yy < doc.Height - 1; yy++)
                        for (int xx = 1; xx < doc.Width - 1; xx++)
                            if (!occupied.Contains(((long)xx << 32) | (uint)yy))
                            { occupied.Add(((long)xx << 32) | (uint)yy); FreeX = xx; FreeY = yy; return true; }
                    return false;
                };

                // 1) delete instance id of doc.Instances[0]
                int delId = doc.Instances[0].Id;
                if (byId.TryGetValue(delId, out var delTag)) UnityEngine.Object.DestroyImmediate(delTag.gameObject);
                else failures.Add("no scene object for delete target id=" + delId);

                // 2) move doc.Instances[1] to a guaranteed-empty cell
                int mvId = doc.Instances[1].Id;
                if (!takeFree()) { failures.Add("no free cell for move"); return ExitFailed; }
                int mcx = FreeX, mcy = FreeY;
                if (byId.TryGetValue(mvId, out var mvTag))
                    mvTag.transform.position = new Vector3(
                        (int)Math.Round((mcx + 0.5) * tile), mvTag.transform.position.y,
                        (int)Math.Round((mcy + 0.5) * tile));
                else failures.Add("no scene object for move target id=" + mvId);

                // 3) hand-add: a tagged object with Id<0 and Source user-added, empty cell
                if (!takeFree()) { failures.Add("no free cell for add"); return ExitFailed; }
                int acx = FreeX, acy = FreeY;
                var addRef = doc.Instances[2];
                var addGo = new GameObject("user_added");
                addGo.transform.SetParent(root.transform, false);
                addGo.transform.position = new Vector3(
                    (int)Math.Round((acx + 0.5) * tile), 0f, (int)Math.Round((acy + 0.5) * tile));
                var addTag = addGo.AddComponent<MapInstanceId>();
                addTag.Id = -1;
                addTag.Source = "user-added";
                addTag.Category = addRef.Category;
                addTag.Type = addRef.Type;

                // Diff -> edits.json
                var differ = new SceneDiffer();
                string editsJson = differ.BuildEditsJson(doc, root);
                Debug.Log($"[LPW] differ ops: delete={differ.DeleteCount} move={differ.MoveCount} add={differ.AddCount}");
                if (differ.DeleteCount != 1 || differ.MoveCount != 1 || differ.AddCount != 1)
                    failures.Add($"differ expected (1,1,1) got ({differ.DeleteCount},{differ.MoveCount},{differ.AddCount})");
                string editsPath = Path.Combine(workDir, "scene_edits.json");
                File.WriteAllText(editsPath, editsJson);

                // Overlay through the generator, then reload.
                var res = OverlayReceiver.Run(repoRoot, baseMap, editsPath, workDir, "scene_roundtrip");
                Debug.Log("[LPW] overlay exit=" + res.ExitCode);
                if (!res.Success)
                {
                    failures.Add("overlay failed (exit " + res.ExitCode + "): " + TrimTail(res.Output, 600));
                }
                else
                {
                    var d2 = MapDocument.Load(res.MapJsonPath);
                    if (d2.Lineage == null || d2.Lineage.Mode != "overlay" || d2.Lineage.OpCount != 3)
                        failures.Add($"lineage wrong: mode={(d2.Lineage?.Mode)} op_count={(d2.Lineage?.OpCount ?? -1)}");
                    int added = 0, moved = 0;
                    foreach (var i in d2.Instances)
                    {
                        if (i.Source == "user-added") added++;
                        else if (i.Source == "user-moved") moved++;
                    }
                    if (added != 1) failures.Add("expected 1 user-added in reloaded doc, got " + added);
                    if (moved != 1) failures.Add("expected 1 user-moved in reloaded doc, got " + moved);
                    int expect = baseCount - 1 + 1;   // one delete, one add
                    if (d2.Instances.Count != expect)
                        failures.Add($"instance count: base {baseCount} -delete +add should be {expect}, got {d2.Instances.Count}");
                }
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                if (root != null) UnityEngine.Object.DestroyImmediate(root);
                EditorUtility.UnloadUnusedAssetsImmediate();
            }

            if (failures.Count > 0)
            {
                foreach (var f in failures) Debug.LogError("[LPW] RT FAIL: " + f);
                Debug.Log("[LPW] ROUNDTRIP_FAIL: " + failures.Count + " issue(s)");
                return ExitFailed;
            }
            Debug.Log("[LPW] ROUNDTRIP_OK: delete+move+add -> edits.json -> overlay -> reload verified");
            return ExitOk;
        }

        static string TrimTail(string s, int n)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Length <= n ? s : s.Substring(s.Length - n);
        }
    }
}
