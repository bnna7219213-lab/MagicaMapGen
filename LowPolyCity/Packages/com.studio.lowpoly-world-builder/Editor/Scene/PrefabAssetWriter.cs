using System.IO;
using LowPolyWorldBuilder.Data;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Saves generated content as Prefab assets and the world as a Scene.
    /// Uses AssetDatabase.StartAssetEditing inside try/finally (plan 6.2).
    /// </summary>
    public static class PrefabAssetWriter
    {
        public static void EnsureFolder(string assetFolder)
        {
            if (AssetDatabase.IsValidFolder(assetFolder)) return;
            var parts = assetFolder.Split('/');
            string cur = parts[0]; // "Assets"
            for (int i = 1; i < parts.Length; i++)
            {
                string next = cur + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(cur, parts[i]);
                cur = next;
            }
        }

        public static GameObject SaveRootAsPrefab(GameObject root, string assetFolder, string name)
        {
            EnsureFolder(assetFolder);
            string path = $"{assetFolder}/{name}.prefab";
            return PrefabUtility.SaveAsPrefabAsset(root, path);
        }

        public static void SaveScene(string assetFolder, string name)
        {
            EnsureFolder(assetFolder);
            string path = $"{assetFolder}/{name}.unity";
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), path);
        }

        public static void WriteReport(WorldBuildReport report, string assetFolder, string name)
        {
            EnsureFolder(assetFolder);
            string json = JsonUtility.ToJson(report, true);
            string summary = report.ToSummaryText();
            AssetDatabase.StartAssetEditing();
            try
            {
                File.WriteAllText(Path.Combine(assetFolder, name + ".report.json"), json);
                File.WriteAllText(Path.Combine(assetFolder, name + ".report.txt"), summary);
            }
            finally
            {
                AssetDatabase.StopAssetEditing();
            }
            AssetDatabase.Refresh();
        }
    }
}
