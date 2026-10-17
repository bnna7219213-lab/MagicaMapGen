using System;
using System.Collections.Generic;
using System.IO;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Editor.Scene;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.UI
{
    /// <summary>
    /// Tools > Low Poly World Builder > Import Map (Path B). The interactive half of
    /// phase 3: pick a map.json, inspect its contract/lineage/source breakdown, build it
    /// into the scene, then run the snapshot diff to edits.json and apply it back through
    /// <c>mapgen --overlay</c>. Delegates all behaviour to MapDocument / SceneAssembler /
    /// SceneDiffer / OverlayReceiver so the window itself holds no logic.
    /// </summary>
    public sealed class MapImportWindow : EditorWindow
    {
        string _mapPath = "";
        string _repoRoot = Environment.GetEnvironmentVariable("MAPGEN_REPO") ?? "";
        MapDocument _doc;
        GameObject _root;
        Vector2 _scroll;
        string _status = "Pick a map.json to import.";
        int _lastExit = -1;

        [MenuItem("Tools/Low Poly World Builder/Import Map (JSON)")]
        public static void Open()
        {
            var w = GetWindow<MapImportWindow>();
            w.titleContent = new GUIContent("Import Map");
            w.minSize = new Vector2(360, 420);
            w.Show();
        }

        void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);
            EditorGUILayout.LabelField("Source document", EditorStyles.boldLabel);
            using (new EditorGUILayout.HorizontalScope())
            {
                _mapPath = EditorGUILayout.TextField(_mapPath);
                if (GUILayout.Button("Browse...", GUILayout.Width(70)))
                {
                    string p = EditorUtility.OpenFilePanel("Select map.json", "", "json");
                    if (!string.IsNullOrEmpty(p)) { _mapPath = p; _doc = null; }
                }
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Load & Preview")) Load();
                if (GUILayout.Button("Build Scene")) Build();
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Diff -> edits.json")) Diff();
                if (GUILayout.Button("Apply overlay & reload")) ApplyOverlay();
            }

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Repo root (holds mapgen/)", _repoRoot);
            _repoRoot = EditorGUILayout.TextField(_repoRoot);

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Status", EditorStyles.boldLabel);
            if (!string.IsNullOrEmpty(_status))
                EditorGUILayout.HelpBox(_status, _lastExit == 0 || _lastExit < 0 ? MessageType.Info : MessageType.Error);

            if (_doc != null) DrawMeta();
            EditorGUILayout.EndScrollView();
        }

        void Load()
        {
            _lastExit = -1;
            try
            {
                _doc = MapDocument.Load(_mapPath);
                _status = "Loaded " + Path.GetFileName(_mapPath);
            }
            catch (Exception ex)
            {
                _doc = null;
                _status = "Load failed: " + ex.Message;
            }
        }

        void Build()
        {
            if (_doc == null) { _status = "Load a map first."; return; }
            var report = new WorldBuildReport
            {
                seed = _doc.Seed, theme = _doc.ThemeId, profileName = Label(),
                gridWidth = _doc.Width, gridHeight = _doc.Height,
            };
            _root = new SceneAssembler().FromJson(_doc, Label(), report);
            Selection.activeObject = _root;
            _status = "Built scene root " + _root.name;
        }

        void Diff()
        {
            if (_doc == null || _root == null) { _status = "Load and build before diffing."; return; }
            var differ = new SceneDiffer();
            string edits = differ.BuildEditsJson(_doc, _root);
            string path = EditsPath();
            File.WriteAllText(path, edits);
            _status = $"edits.json: delete={differ.DeleteCount} move={differ.MoveCount} "
                    + $"add={differ.AddCount} rotate={differ.RotateCount} -> {Path.GetFileName(path)}";
        }

        void ApplyOverlay()
        {
            if (_doc == null) { _status = "Load a map first."; return; }
            if (string.IsNullOrEmpty(_repoRoot) || !Directory.Exists(_repoRoot))
            { _status = "Set a valid repo root that holds mapgen/."; return; }
            string editsPath = EditsPath();
            if (!File.Exists(editsPath)) { _status = "Run Diff first to create edits.json."; return; }
            var res = OverlayReceiver.Run(_repoRoot, _mapPath, editsPath,
                Path.GetDirectoryName(_mapPath), Label() + "_edited");
            _lastExit = res.ExitCode;
            if (res.Success)
            {
                _doc = MapDocument.Load(res.MapJsonPath);
                _mapPath = res.MapJsonPath;
                if (_root != null) DestroyImmediate(_root);
                _root = null;
                _status = "Overlay applied; reloaded " + Path.GetFileName(res.MapJsonPath);
            }
            else
            {
                _status = "Overlay failed (" + ExplainExit(res.ExitCode) + ")";
            }
        }

        void DrawMeta()
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Metadata", EditorStyles.boldLabel);
            EditorGUILayout.LabelField("theme / seed", _doc.ThemeId + " / " + _doc.Seed);
            EditorGUILayout.LabelField("grid", _doc.Width + " x " + _doc.Height);
            EditorGUILayout.LabelField("schema", "v" + _doc.SchemaVersion + "  (gen " + _doc.GeneratorVersion + ")");
            EditorGUILayout.LabelField("contract", _doc.ContractSummary);
            if (_doc.Lineage != null)
                EditorGUILayout.LabelField("lineage", _doc.Lineage.Mode + " ops=" + _doc.Lineage.OpCount);
            var counts = new Dictionary<string, int>();
            foreach (var i in _doc.Instances)
                counts[i.Source] = counts.TryGetValue(i.Source, out int c) ? c + 1 : 1;
            int total = _doc.Instances.Count;
            string s = "";
            foreach (var kv in counts) s += kv.Key + "=" + kv.Value + "  ";
            EditorGUILayout.LabelField("instances", total + "  (" + s.Trim() + ")");
        }

        string Label() => Path.GetFileNameWithoutExtension(_mapPath);
        string EditsPath() => Path.Combine(Path.GetDirectoryName(_mapPath) ?? ".", "scene_edits.json");

        static string ExplainExit(int code) => code switch
        {
            0 => "success",
            1 => "contract failed - theme guarantees violated",
            2 => "configuration / bad edits or base",
            3 => "generation runtime error",
            4 => "output failed map.schema.json validation",
            _ => "unknown exit " + code,
        };
    }
}
