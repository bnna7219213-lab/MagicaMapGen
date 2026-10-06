using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Palette materials, created once per build (in-memory for preview, saved
    /// as assets only when the user saves the world).
    /// </summary>
    public sealed class MaterialFactory
    {
        readonly Dictionary<string, Material> _cache = new Dictionary<string, Material>();
        readonly StylePalette _palette;
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly int ColorId = Shader.PropertyToID("_Color");

        public MaterialFactory(StylePalette palette) { _palette = palette; }

        public Material Get(string key, Color color)
        {
            if (_cache.TryGetValue(key, out var m) && m != null) return m;
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) shader = Shader.Find("Standard");
            m = new Material(shader) { name = "LPW_" + key };
            if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, color);
            else if (m.HasProperty(ColorId)) m.SetColor(ColorId, color);
            _cache[key] = m;
            return m;
        }

        public Material Road() => Get("road", _palette.road);
        public Material Marking() => Get("marking", _palette.roadMarking);
        public Material Sidewalk() => Get("sidewalk", _palette.sidewalk);
        public Material Ground() => Get("ground", _palette.ground);
        public Material Window() => Get("window", _palette.window);
        public Material Foliage() => Get("foliage", _palette.foliage);
        public Material Trunk() => Get("trunk", _palette.trunk);
        public Material Lamp() => Get("lamp", _palette.lampPost);
        public Material Wall(int i)
        {
            var arr = _palette.buildingWalls;
            var c = arr != null && arr.Length > 0 ? arr[Mathf.Abs(i) % arr.Length] : Color.gray;
            return Get("wall" + i, c);
        }
        public Material Roof(int i)
        {
            var arr = _palette.buildingRoofs;
            var c = arr != null && arr.Length > 0 ? arr[Mathf.Abs(i) % arr.Length] : Color.gray;
            return Get("roof" + i, c);
        }
        public Material Accent() => Get("building_accent", _palette.buildingAccent);
        public Material Glass() => Get("building_glass", _palette.buildingGlass);

        public Material[] BuildingMats(int wall, int roof)
            => new[] { Wall(wall), Roof(roof), Window(), Glass(), Accent() };
        public Material[] RoadMats()
            => new[] { Road(), Marking(), Sidewalk(), Ground() };
        public Material[] TreeMats() => new[] { Trunk(), Foliage() };
        public Material[] LampMats() => new[] { Lamp() };
    }
}
