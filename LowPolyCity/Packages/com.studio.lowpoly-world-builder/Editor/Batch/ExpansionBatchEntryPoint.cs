using System;
using System.Collections.Generic;
using System.Diagnostics;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Editor.Scene;
using LowPolyWorldBuilder.Editor.UI;
using LowPolyWorldBuilder.Editor.Validation;
using LowPolyWorldBuilder.Generation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace LowPolyWorldBuilder.Editor.Batch
{
    /// <summary>Generates the five 4x4 themes and the same five themes at 16x16.</summary>
    public static class ExpansionBatchEntryPoint
    {
        public static void GenerateExpansionPack()
        {
            var failures = new List<string>();
            try
            {
                var profiles = ExpansionScenarioFactory.CreateProfiles();
                var profilePaths = new List<string>();
                foreach (var profile in profiles)
                    profilePaths.Add(AssetDatabase.GetAssetPath(profile));

                for (int i = 0; i < profilePaths.Count; i++)
                {
                    var profile = AssetDatabase.LoadAssetAtPath<WorldBuildProfile>(profilePaths[i]);
                    if (profile == null) throw new InvalidOperationException("Could not reload profile: " + profilePaths[i]);
                    var timer = Stopwatch.StartNew();
                    var report = new WorldBuildReport
                    {
                        seed = profile.seed,
                        profileName = profile.name,
                        theme = profile.theme.ToString(),
                        gridWidth = profile.blockCount.x,
                        gridHeight = profile.blockCount.y,
                        timestampUtc = DateTime.UtcNow
                    };

                    if (!ProfileValidator.Validate(profile, report) |
                        !AssetCatalogValidator.Validate(profile.catalog, report))
                    {
                        timer.Stop();
                        report.buildDurationMilliseconds = timer.ElapsedMilliseconds;
                        PrefabAssetWriter.WriteReport(report, profile.outputFolder, profile.worldName);
                        failures.Add(profile.worldName + ": validation failed");
                        continue;
                    }

                    EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                    var plan = new WorldPlanGenerator().Generate(profile, report);
                    string guid = AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(profile));
                    var root = new SceneAssembler().Assemble(profile, plan, guid, report, registerUndo: false);
                    FrameCamera(profile);

                    PrefabAssetWriter.EnsureFolder(profile.outputFolder);
                    PrefabAssetWriter.SaveRootAsPrefab(root, profile.outputFolder, profile.worldName);
                    PrefabAssetWriter.SaveScene(profile.outputFolder, profile.worldName);
                    timer.Stop();
                    report.buildDurationMilliseconds = timer.ElapsedMilliseconds;
                    PrefabAssetWriter.WriteReport(report, profile.outputFolder, profile.worldName);
                    Debug.Log("[LPW] Expansion scene complete:\n" + report.ToSummaryText());

                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    EditorUtility.UnloadUnusedAssetsImmediate();
                    GC.Collect();
                }

                AssetDatabase.SaveAssets();
            }
            catch (Exception ex)
            {
                Debug.LogError("[LPW] Expansion generation exception: " + ex);
                failures.Add(ex.Message);
            }

            if (failures.Count > 0)
                Debug.LogError("[LPW] Expansion failures: " + string.Join("; ", failures));
            else
                Debug.Log("[LPW] All 10 expansion scenarios generated successfully.");

            if (Application.isBatchMode)
                EditorApplication.Exit(failures.Count > 0 ? 2 : 0);
        }

        static void FrameCamera(WorldBuildProfile profile)
        {
            var camera = Camera.main;
            if (camera == null)
            {
                var go = new GameObject("Main Camera");
                camera = go.AddComponent<Camera>();
                go.tag = "MainCamera";
            }

            Vector3 target = new Vector3(profile.WorldSizeX * 0.5f, 0f, profile.WorldSizeZ * 0.5f);
            float scale = Mathf.Max(profile.WorldSizeX, profile.WorldSizeZ);
            camera.transform.position = target + new Vector3(scale * 0.78f, scale * 0.84f, -scale * 0.95f);
            camera.transform.rotation = Quaternion.LookRotation(target - camera.transform.position, Vector3.up);
            camera.fieldOfView = 55f;
            camera.nearClipPlane = 0.3f;
            camera.farClipPlane = scale * 5f;
        }
    }
}
