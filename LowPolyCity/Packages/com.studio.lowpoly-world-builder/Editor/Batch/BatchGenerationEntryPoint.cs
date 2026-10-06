using System;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using LowPolyWorldBuilder.Editor.Scene;
using LowPolyWorldBuilder.Editor.Validation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Batch
{
    /// <summary>
    /// Static entry for Unity batch mode:
    ///   Unity.exe -batchmode -quit -projectPath <proj>
    ///     -executeMethod LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateWorld
    ///     -lpwProfile "Assets/.../Profile.asset" [-lpwOut "Assets/Out"] [-lpwSeed 42]
    /// Exit code: 0 success, 2 validation failure, 3 missing profile,
    /// 4 generation exception.
    /// </summary>
    public static class BatchGenerationEntryPoint
    {
        /// <summary>
        /// Zero-argument smoke entry: creates the default 4x4 profile if the
        /// project has none, then runs the full batch generation. Used by CI:
        ///   Unity.exe -batchmode -quit -projectPath <proj>
        ///     -executeMethod LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateDefaultDemo
        /// </summary>
        public static void GenerateDefaultDemo()
        {
            try
            {
                var profile = LowPolyWorldBuilder.Editor.UI.SampleAssetFactory.CreateDefaultProfileWithZones();
                string path = AssetDatabase.GetAssetPath(profile);
                System.Environment.SetEnvironmentVariable("LPW_DEFAULT_PROFILE", path);
                // Reuse the standard path with explicit args injected.
                var args = new System.Collections.Generic.List<string>(System.Environment.GetCommandLineArgs());
                args.Add("-lpwProfile"); args.Add(path);
                var opts = CommandLineOptions.Parse(args.ToArray());
                GenerateWorldWith(opts);
            }
            catch (Exception ex)
            {
                Debug.LogError("[LPW] Demo generation exception: " + ex);
                Exit(4);
            }
        }

        public static void GenerateWorld()
        {
            GenerateWorldWith(CommandLineOptions.FromEnvironment());
        }

        static void GenerateWorldWith(CommandLineOptions opts)
        {
            try
            {
                if (string.IsNullOrEmpty(opts.ProfilePath))
                {
                    Debug.LogError("[LPW] Missing -lpwProfile argument");
                    Exit(3);
                    return;
                }
                var profile = AssetDatabase.LoadAssetAtPath<WorldBuildProfile>(opts.ProfilePath);
                if (profile == null)
                {
                    Debug.LogError("[LPW] Profile not found: " + opts.ProfilePath);
                    Exit(3);
                    return;
                }
                if (opts.SeedOverride.HasValue) profile.seed = opts.SeedOverride.Value;
                if (!string.IsNullOrEmpty(opts.OutputFolder)) profile.outputFolder = opts.OutputFolder;

                var report = new WorldBuildReport
                {
                    seed = profile.seed,
                    profileName = profile.name,
                    timestampUtc = DateTime.UtcNow
                };

                if (!ProfileValidator.Validate(profile, report) |
                    !AssetCatalogValidator.Validate(profile.catalog, report))
                {
                    Debug.LogError("[LPW] Validation failed:\n" + report.ToSummaryText());
                    PrefabAssetWriter.WriteReport(report, profile.outputFolder, profile.worldName);
                    Exit(2);
                    return;
                }

                var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                var plan = new WorldPlanGenerator().Generate(profile, report);
                string guid = AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(profile));
                var root = new SceneAssembler().Assemble(profile, plan, guid, report, registerUndo: false);

                PrefabAssetWriter.EnsureFolder(profile.outputFolder);
                PrefabAssetWriter.SaveRootAsPrefab(root, profile.outputFolder, profile.worldName);
                PrefabAssetWriter.SaveScene(profile.outputFolder, profile.worldName);
                PrefabAssetWriter.WriteReport(report, profile.outputFolder, profile.worldName);

                Debug.Log("[LPW] Generation complete:\n" + report.ToSummaryText());
                Exit(report.HasErrors ? 2 : 0);
            }
            catch (Exception ex)
            {
                Debug.LogError("[LPW] Generation exception: " + ex);
                Exit(4);
            }
        }

        static void Exit(int code)
        {
            if (Application.isBatchMode)
                EditorApplication.Exit(code);
        }
    }
}
