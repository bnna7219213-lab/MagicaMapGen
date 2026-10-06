using System;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using LowPolyWorldBuilder.Editor.Preview;
using LowPolyWorldBuilder.Editor.Scene;
using LowPolyWorldBuilder.Editor.Validation;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

namespace LowPolyWorldBuilder.Editor.UI
{
    /// <summary>
    /// Tools > Low Poly World Builder. IMGUI container inside UI Toolkit root:
    /// config fields, validation warnings, stats and Preview / Generate /
    /// Rebuild / Clean / Save buttons (plan 3.1 item 1).
    /// </summary>
    public sealed class WorldBuilderWindow : UnityEditor.EditorWindow
    {
        WorldBuildProfile _profile;
        UnityEditor.Editor _profileEditor;
        PreviewController _preview = new PreviewController();
        Vector2 _scroll;
        string _status = "Select or create a WorldBuildProfile.";
        WorldBuildReport _lastReport;

        [MenuItem("Tools/Low Poly World Builder")]
        public static void Open()
        {
            var w = GetWindow<WorldBuilderWindow>();
            w.titleContent = new GUIContent("Low Poly World Builder");
            w.minSize = new Vector2(360, 480);
            w.Show();
        }

        void OnEnable() { _preview = _preview ?? new PreviewController(); }
        void OnDisable() { /* keep preview; explicit Clear Preview button */ }

        void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("World Configuration", EditorStyles.boldLabel);
            EditorGUI.BeginChangeCheck();
            _profile = (WorldBuildProfile)EditorGUILayout.ObjectField("Profile", _profile, typeof(WorldBuildProfile), false);
            if (EditorGUI.EndChangeCheck()) _profileEditor = null;

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Create Default Profile"))
                    _profile = SampleAssetFactory.CreateDefaultProfileWithZones();
                if (GUILayout.Button("Clear Preview"))
                { _preview.Clear(); _status = "Preview cleared."; }
            }

            if (_profile == null)
            {
                EditorGUILayout.HelpBox(_status + "\n\nAssign a WorldBuildProfile asset or create a default one.", MessageType.Info);
                EditorGUILayout.EndScrollView();
                return;
            }

            // Inline profile inspector
            if (_profileEditor == null)
                UnityEditor.Editor.CreateCachedEditor(_profile, null, ref _profileEditor);
            if (_profileEditor != null)
            {
                EditorGUILayout.Space();
                _profileEditor.OnInspectorGUI();
            }

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Actions", EditorStyles.boldLabel);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Preview (proxy)")) DoPreview();
                if (GUILayout.Button("Generate")) DoGenerate(save: false);
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Generate + Save Scene/Prefab/Report")) DoGenerate(save: true);
                if (GUILayout.Button("Clean Generated")) DoClean();
            }

            EditorGUILayout.Space();
            EditorGUILayout.HelpBox(_status, _lastReport != null && _lastReport.HasErrors ? MessageType.Error : MessageType.None);

            EditorGUILayout.EndScrollView();
        }

        void DoPreview()
        {
            var report = StartReport();
            if (!Validate(report)) { _status = report.ToSummaryText(); return; }
            _preview.ShowPreview(_profile);
            _status = $"Preview shown (seed {_profile.seed}). {report.blockCount} blocks / {report.lotCount} lots planned.";
        }

        void DoGenerate(bool save)
        {
            var report = StartReport();
            if (!Validate(report)) { _status = report.ToSummaryText(); return; }
            _preview.Clear();

            var plan = new WorldPlanGenerator().Generate(_profile, report);
            string path = AssetDatabase.GetAssetPath(_profile);
            string guid = AssetDatabase.AssetPathToGUID(path);

            var root = new SceneAssembler().Assemble(_profile, plan, guid, report, registerUndo: true);
            Undo.RegisterCreatedObjectUndo(root, "Generate Low Poly World");

            if (save)
            {
                PrefabAssetWriter.EnsureFolder(_profile.outputFolder);
                PrefabAssetWriter.SaveRootAsPrefab(root, _profile.outputFolder, _profile.worldName);
                PrefabAssetWriter.SaveScene(_profile.outputFolder, _profile.worldName);
                PrefabAssetWriter.WriteReport(report, _profile.outputFolder, _profile.worldName);
            }

            _status = report.ToSummaryText();
            if (!save) _status += "\n(Not saved — use 'Generate + Save' to persist scene/prefab/report.)";
        }

        void DoClean()
        {
            string path = AssetDatabase.GetAssetPath(_profile);
            string guid = AssetDatabase.AssetPathToGUID(path);
            int removed = GeneratedRootManager.CleanAll(guid);
            _status = $"Removed {removed} generated root(s). Locked nodes were preserved.";
        }

        WorldBuildReport StartReport()
        {
            _lastReport = new WorldBuildReport
            {
                seed = _profile.seed,
                profileName = _profile.name,
                timestampUtc = DateTime.UtcNow
            };
            return _lastReport;
        }

        bool Validate(WorldBuildReport report)
        {
            bool ok = ProfileValidator.Validate(_profile, report);
            ok &= AssetCatalogValidator.Validate(_profile.catalog, report);
            return ok;
        }
    }
}
