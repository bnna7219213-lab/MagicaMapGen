using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Geometry;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>Creates the signature transport structures for each world theme as compact meshes.</summary>
    public sealed class ThemedInfrastructureAssembler
    {
        const int Water = 0;
        const int Concrete = 1;
        const int Steel = 2;
        const int Asphalt = 3;
        const int Marking = 4;
        const int Accent = 5;
        const int Glass = 6;
        const int CargoRed = 7;
        const int CargoBlue = 8;
        const int CargoYellow = 9;

        public void Assemble(WorldBuildProfile profile, BuildPlan plan, Transform parent, MaterialFactory mats)
        {
            if (profile.theme == WorldTheme.City) return;

            var mesh = new MeshBuilder();
            switch (profile.theme)
            {
                case WorldTheme.Railway: BuildRailway(profile, mesh); break;
                case WorldTheme.Metro: BuildMetro(profile, mesh); break;
                case WorldTheme.Harbor: BuildHarbor(profile, plan, mesh); break;
                case WorldTheme.Airport: BuildAirport(profile, mesh); break;
            }

            var root = new GameObject(profile.theme + " Infrastructure");
            root.transform.SetParent(parent, false);
            root.AddComponent<MeshFilter>().sharedMesh = mesh.Build("LPW_" + profile.theme + "_Infrastructure");
            root.AddComponent<MeshRenderer>().sharedMaterials = new[]
            {
                mats.Get("theme_water", new Color(0.12f, 0.48f, 0.72f)),
                mats.Get("theme_concrete", new Color(0.72f, 0.72f, 0.67f)),
                mats.Get("theme_steel", new Color(0.24f, 0.29f, 0.32f)),
                mats.Get("theme_asphalt", new Color(0.18f, 0.19f, 0.22f)),
                mats.Get("theme_marking", new Color(0.98f, 0.9f, 0.56f)),
                mats.Get("theme_accent", new Color(0.95f, 0.46f, 0.18f)),
                mats.Get("theme_glass", new Color(0.31f, 0.72f, 0.84f)),
                mats.Get("theme_cargo_red", new Color(0.78f, 0.25f, 0.19f)),
                mats.Get("theme_cargo_blue", new Color(0.2f, 0.4f, 0.75f)),
                mats.Get("theme_cargo_yellow", new Color(0.94f, 0.68f, 0.18f))
            };
        }

        static void BuildRailway(WorldBuildProfile p, MeshBuilder m)
        {
            float y = 0.15f, z = p.WorldSizeZ * 0.5f, length = p.WorldSizeX;
            m.AddBox(Concrete, new Vector3(length * 0.5f, y, z), new Vector3(length, 0.3f, 9f));
            AddTrackX(m, length, z, y + 0.3f);

            float center = length * 0.5f;
            m.AddBox(Concrete, new Vector3(center, 1.1f, z + 7f), new Vector3(58f, 1.5f, 4.5f));
            m.AddBox(Accent, new Vector3(center, 7f, z + 7f), new Vector3(48f, 0.7f, 10f));
            for (float x = center - 22f; x <= center + 22f; x += 11f)
                m.AddBox(Concrete, new Vector3(x, 4f, z + 7f), new Vector3(0.65f, 6f, 0.65f));

            for (int car = 0; car < 4; car++)
            {
                float x = center + (car - 1.5f) * 17f;
                m.AddBox(Accent, new Vector3(x, 3.2f, z), new Vector3(15.5f, 4.2f, 4.8f));
                m.AddBox(Concrete, new Vector3(x, 5.45f, z), new Vector3(14.5f, 0.4f, 4.4f));
                for (float wx = x - 5f; wx <= x + 5f; wx += 3.4f)
                    m.AddBox(Glass, new Vector3(wx, 3.8f, z - 2.42f), new Vector3(2.2f, 1.2f, 0.1f));
            }
        }

        static void BuildMetro(WorldBuildProfile p, MeshBuilder m)
        {
            float x = p.WorldSizeX * 0.5f, length = p.WorldSizeZ;
            // Open-top cutaway tunnel keeps the underground train inspectable in the Scene view.
            m.AddBox(Asphalt, new Vector3(x, -5.4f, length * 0.5f), new Vector3(11f, 0.5f, length));
            m.AddBox(Concrete, new Vector3(x - 5.2f, -2.2f, length * 0.5f), new Vector3(0.8f, 6f, length));
            m.AddBox(Concrete, new Vector3(x + 5.2f, -2.2f, length * 0.5f), new Vector3(0.8f, 6f, length));
            AddTrackZ(m, length, x, -5.0f);

            for (int car = 0; car < 3; car++)
            {
                float z = length * 0.5f + (car - 1) * 17f;
                m.AddBox(Accent, new Vector3(x, -2.8f, z), new Vector3(4.6f, 3.4f, 15.5f));
                m.AddBox(Concrete, new Vector3(x, -0.95f, z), new Vector3(4.2f, 0.35f, 15f));
                for (float wz = z - 5f; wz <= z + 5f; wz += 3.2f)
                    m.AddBox(Glass, new Vector3(x - 2.33f, -2.5f, wz), new Vector3(0.1f, 1.15f, 2f));
            }

            AddMetroEntrance(m, x - 17f, length * 0.5f - 25f);
            AddMetroEntrance(m, x + 17f, length * 0.5f + 25f);
        }

        static void AddMetroEntrance(MeshBuilder m, float x, float z)
        {
            m.AddBox(Concrete, new Vector3(x, 0.8f, z), new Vector3(9f, 1.5f, 8f));
            m.AddBox(Glass, new Vector3(x, 1.8f, z - 3.7f), new Vector3(7f, 1.1f, 0.25f));
            m.AddBox(Accent, new Vector3(x, 2.8f, z + 3f), new Vector3(6f, 0.35f, 2f));
        }

        static void BuildHarbor(WorldBuildProfile p, BuildPlan plan, MeshBuilder m)
        {
            float minX = float.MaxValue, minZ = float.MaxValue, maxX = 0f, maxZ = 0f;
            foreach (var b in plan.blocks)
            {
                if (!b.infrastructureBlock) continue;
                minX = Mathf.Min(minX, b.rect.xMin);
                minZ = Mathf.Min(minZ, b.rect.yMin);
                maxX = Mathf.Max(maxX, b.rect.xMax);
                maxZ = Mathf.Max(maxZ, b.rect.yMax);
            }
            if (minX == float.MaxValue) return;

            float width = maxX - minX, height = maxZ - minZ;
            // Water patches stay within reserved blocks, leaving the surrounding streets clear.
            foreach (var b in plan.blocks)
                if (b.infrastructureBlock)
                    m.AddQuad(Water, new Vector3(b.rect.xMin + 2f, 0.035f, b.rect.yMin + 2f),
                        new Vector3(b.rect.xMax - 2f, 0.035f, b.rect.yMin + 2f),
                        new Vector3(b.rect.xMax - 2f, 0.035f, b.rect.yMax - 2f),
                        new Vector3(b.rect.xMin + 2f, 0.035f, b.rect.yMax - 2f), Vector3.up);

            float pierX = minX + width * 0.48f, pierZ = minZ + height * 0.5f;
            m.AddBox(Concrete, new Vector3(pierX, 0.65f, pierZ), new Vector3(width * 0.72f, 1.1f, 7f));
            for (int berth = 0; berth < 3; berth++)
            {
                float z = minZ + height * (0.25f + berth * 0.24f);
                m.AddBox(Accent, new Vector3(minX + width * 0.42f, 1.15f, z), new Vector3(28f, 1.2f, 10f));
                m.AddBox(Concrete, new Vector3(minX + width * 0.42f, 2.15f, z), new Vector3(22f, 0.9f, 8f));
                m.AddBox(CargoRed, new Vector3(pierX + 4f, 4.1f, z - 2f), new Vector3(6f, 3.8f, 5f));
                m.AddBox(CargoBlue, new Vector3(pierX - 3f, 4.1f, z + 2f), new Vector3(6f, 3.8f, 5f));
                m.AddBox(CargoYellow, new Vector3(pierX + 11f, 4.1f, z + 2f), new Vector3(6f, 3.8f, 5f));
            }
            AddCrane(m, minX + width * 0.78f, pierZ);
            AddCrane(m, minX + width * 0.2f, pierZ);
        }

        static void AddCrane(MeshBuilder m, float x, float z)
        {
            m.AddBox(Accent, new Vector3(x, 10f, z), new Vector3(1.4f, 19f, 1.4f));
            m.AddBox(Accent, new Vector3(x + 6f, 19.5f, z), new Vector3(14f, 1.3f, 1.3f));
            m.AddBox(Concrete, new Vector3(x + 12f, 15f, z), new Vector3(0.8f, 9f, 0.8f));
            m.AddBox(Concrete, new Vector3(x + 3f, 0.8f, z), new Vector3(8f, 1.6f, 6f));
        }

        static void BuildAirport(WorldBuildProfile p, MeshBuilder m)
        {
            float length = p.WorldSizeX, runwayZ = p.roadWidth + p.blockSize * 0.5f;
            m.AddBox(Asphalt, new Vector3(length * 0.5f, 0.18f, runwayZ), new Vector3(length - 8f, 0.35f, 24f));
            m.AddBox(Concrete, new Vector3(length * 0.5f, 0.08f, runwayZ), new Vector3(length - 16f, 0.12f, 30f));
            for (float x = 22f; x < length - 22f; x += 22f)
                m.AddBox(Marking, new Vector3(x, 0.38f, runwayZ), new Vector3(9f, 0.04f, 0.45f));
            for (float x = 18f; x < length - 18f; x += 3f)
            {
                m.AddBox(Marking, new Vector3(x, 0.39f, runwayZ - 9f), new Vector3(1.1f, 0.04f, 1.1f));
                m.AddBox(Marking, new Vector3(x, 0.39f, runwayZ + 9f), new Vector3(1.1f, 0.04f, 1.1f));
            }

            float terminalX = Mathf.Min(p.blockSize * 0.5f + p.roadWidth, length * 0.3f);
            float terminalZ = p.roadWidth + p.Pitch + p.blockSize * 0.5f;
            m.AddBox(Concrete, new Vector3(terminalX, 5f, terminalZ), new Vector3(42f, 9f, 24f));
            m.AddBox(Glass, new Vector3(terminalX, 6f, terminalZ - 12.2f), new Vector3(38f, 5f, 0.3f));
            m.AddBox(Accent, new Vector3(terminalX, 10f, terminalZ), new Vector3(44f, 0.8f, 26f));
            m.AddBox(Concrete, new Vector3(terminalX + 32f, 13f, terminalZ + 3f), new Vector3(7f, 26f, 7f));
            m.AddBox(Glass, new Vector3(terminalX + 32f, 26.5f, terminalZ + 3f), new Vector3(8f, 1f, 8f));

            float planeX = length * 0.65f;
            AddPlane(m, planeX, runwayZ + 12f);
            AddPlane(m, length * 0.82f, runwayZ - 11f);
        }

        static void AddPlane(MeshBuilder m, float x, float z)
        {
            m.AddBox(Glass, new Vector3(x, 3.2f, z), new Vector3(16f, 2.3f, 2.8f));
            m.AddBox(Concrete, new Vector3(x, 2.8f, z), new Vector3(9f, 0.35f, 18f));
            m.AddBox(Accent, new Vector3(x - 8.2f, 3f, z), new Vector3(1.2f, 2f, 3.4f));
            m.AddBox(Accent, new Vector3(x + 7.6f, 3.2f, z), new Vector3(2f, 2.6f, 1.5f));
            m.AddBox(Accent, new Vector3(x + 1f, 4.7f, z), new Vector3(3f, 0.5f, 0.6f));
        }

        static void AddTrackX(MeshBuilder m, float length, float z, float y)
        {
            for (float x = 2f; x < length; x += 4f)
                m.AddBox(Concrete, new Vector3(x, y, z), new Vector3(1.6f, 0.25f, 7f));
            for (float dz = -1.6f; dz <= 1.6f; dz += 3.2f)
                m.AddBox(Steel, new Vector3(length * 0.5f, y + 0.34f, z + dz), new Vector3(length, 0.38f, 0.34f));
        }

        static void AddTrackZ(MeshBuilder m, float length, float x, float y)
        {
            for (float z = 2f; z < length; z += 4f)
                m.AddBox(Concrete, new Vector3(x, y, z), new Vector3(7f, 0.25f, 1.6f));
            for (float dx = -1.6f; dx <= 1.6f; dx += 3.2f)
                m.AddBox(Steel, new Vector3(x + dx, y + 0.34f, length * 0.5f), new Vector3(0.34f, 0.38f, length));
        }
    }
}
