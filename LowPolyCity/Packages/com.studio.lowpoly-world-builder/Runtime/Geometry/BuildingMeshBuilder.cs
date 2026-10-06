using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Geometry
{
    /// <summary>
    /// Submesh slots for building meshes (material array ordering).
    /// BuildingMats() in MaterialFactory must match this order.
    /// </summary>
    public static class BuildingSubmeshes
    {
        public const int Walls = 0;
        public const int Roof = 1;
        public const int Windows = 2;
        public const int Glass = 3;      // curtain walls, storefronts, cabs
        public const int Accent = 4;     // canopies, trim, silo metal, hangar doors
        public const int Count = 5;
    }

    /// <summary>
    /// Builds one merged mesh per building. The LotData.archetype selects a
    /// distinct massing strategy (pitched house, slab apartment, curtain-wall
    /// office, storefront retail, sawtooth warehouse, arched hangar, canopy
    /// station, shaft+cab control tower, cylindrical silo cluster, glass-band
    /// terminal) so zones are visually distinguishable.
    /// </summary>
    public sealed class BuildingMeshBuilder
    {
        public Mesh Build(LotData lot, string name)
        {
            var mb = new MeshBuilder();
            switch (lot.archetype)
            {
                case BuildingArchetype.House: BuildHouse(mb, lot); break;
                case BuildingArchetype.Apartment: BuildApartment(mb, lot); break;
                case BuildingArchetype.Office: BuildOffice(mb, lot); break;
                case BuildingArchetype.Retail: BuildRetail(mb, lot); break;
                case BuildingArchetype.Warehouse: BuildWarehouse(mb, lot); break;
                case BuildingArchetype.Hangar: BuildHangar(mb, lot); break;
                case BuildingArchetype.Station: BuildStation(mb, lot); break;
                case BuildingArchetype.ControlTower: BuildControlTower(mb, lot); break;
                case BuildingArchetype.Silo: BuildSilo(mb, lot); break;
                case BuildingArchetype.Terminal: BuildTerminal(mb, lot); break;
                case BuildingArchetype.MetroTower: BuildMetroTower(mb, lot); break;
                case BuildingArchetype.MetroStation: BuildMetroStation(mb, lot); break;
                case BuildingArchetype.RailDepot: BuildRailDepot(mb, lot); break;
                case BuildingArchetype.HarborWarehouse: BuildHarborWarehouse(mb, lot); break;
                case BuildingArchetype.HarborSilo: BuildHarborSilo(mb, lot); break;
                case BuildingArchetype.Lighthouse: BuildLighthouse(mb, lot); break;
                default: BuildHouse(mb, lot); break;
            }
            return mb.Build(name);
        }

        // ------------------------------------------------------------------
        // Shared helpers
        // ------------------------------------------------------------------

        static Vector3 BodySize(LotData lot, float inset)
        {
            Rect r = lot.rect;
            return new Vector3(r.width * inset, lot.height, r.height * inset);
        }

        static void AddWindowGrid(MeshBuilder mb, Vector3 bodySize, float height,
                                  float floorH, float winW, float winH, float spacing,
                                  int submesh, float groundSkip = 0f)
        {
            float hx = bodySize.x * 0.5f, hz = bodySize.z * 0.5f;
            int floors = Mathf.Max(1, Mathf.FloorToInt((height - 1.2f - groundSkip) / floorH));

            for (int f = 0; f < floors; f++)
            {
                float y = groundSkip + 1.0f + f * floorH + winH * 0.5f;
                if (y + winH * 0.5f > height - 0.4f) break;

                for (float x = -hx + spacing * 0.5f; x + winW * 0.5f < hx; x += spacing)
                {
                    AddWinQuad(mb, submesh, new Vector3(x, y, hz + 0.02f), Vector3.forward, winW, winH);
                    AddWinQuad(mb, submesh, new Vector3(-x, y, -hz - 0.02f), Vector3.back, winW, winH);
                }
                for (float z = -hz + spacing * 0.5f; z + winW * 0.5f < hz; z += spacing)
                {
                    AddWinQuad(mb, submesh, new Vector3(hx + 0.02f, y, z), Vector3.right, winW, winH);
                    AddWinQuad(mb, submesh, new Vector3(-hx - 0.02f, y, -z), Vector3.left, winW, winH);
                }
            }
        }

        static void AddWinQuad(MeshBuilder mb, int submesh, Vector3 center, Vector3 normal, float w, float h)
        {
            Vector3 right = Vector3.Cross(Vector3.up, normal).normalized * (w * 0.5f);
            Vector3 up = Vector3.up * (h * 0.5f);
            mb.AddQuad(submesh,
                center - right - up, center + right - up,
                center + right + up, center - right + up, normal);
        }

        static void FlatRoof(MeshBuilder mb, Vector3 bodySize, float h, float parapet)
        {
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + parapet * 0.5f, 0),
                new Vector3(bodySize.x + 0.5f, parapet, bodySize.z + 0.5f));
        }

        static void PitchedRoof(MeshBuilder mb, Vector3 bodySize, float h, float roofH)
        {
            mb.AddPyramid(BuildingSubmeshes.Roof, new Vector3(0, h, 0),
                Mathf.Min(bodySize.x, bodySize.z) * 0.5f, roofH);
        }

        // ------------------------------------------------------------------
        // Archetypes
        // ------------------------------------------------------------------

        static void BuildHouse(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 4f, 12f);
            var body = BodySize(lot, 0.8f);
            body.y = h;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            PitchedRoof(mb, body, h, Mathf.Clamp(h * 0.45f, 1.8f, 4f));
            AddWindowGrid(mb, body, h, 2.8f, 1.1f, 1.3f, 2.2f, BuildingSubmeshes.Windows);
            // Door on the facing side (+Z before world rotation).
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, 1.1f, body.z * 0.5f + 0.05f),
                new Vector3(1.2f, 2.2f, 0.12f));
            // Chimney on some houses.
            if (lot.styleRoll > 0.45f)
                mb.AddBox(BuildingSubmeshes.Roof, new Vector3(body.x * 0.25f, h + 1.6f, 0),
                    new Vector3(0.7f, 2.2f, 0.7f));
        }

        static void BuildApartment(MeshBuilder mb, LotData lot)
        {
            float h = lot.height;
            var body = BodySize(lot, 0.9f);
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            FlatRoof(mb, body, h, 0.5f);
            AddWindowGrid(mb, body, h, 3.0f, 1.3f, 1.5f, 2.4f, BuildingSubmeshes.Windows);

            // Balcony strips on the facing side every floor.
            float hz = body.z * 0.5f;
            int floors = Mathf.Max(1, Mathf.FloorToInt((h - 1.2f) / 3.0f));
            for (int f = 1; f < floors; f++)
            {
                float y = 1.0f + f * 3.0f;
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, y, hz + 0.55f),
                    new Vector3(body.x * 0.86f, 0.18f, 1.1f));
            }
            // Roof stair bulkhead.
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(body.x * 0.28f, h + 1.1f, 0),
                new Vector3(2.6f, 1.7f, 2.4f));
        }

        static void BuildOffice(MeshBuilder mb, LotData lot)
        {
            float h = lot.height;
            var body = BodySize(lot, 0.92f);
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            FlatRoof(mb, body, h, 0.4f);

            // Curtain wall: continuous horizontal glass bands.
            float hx = body.x * 0.5f, hz = body.z * 0.5f;
            for (float y = 1.8f; y < h - 1f; y += 3.1f)
            {
                AddWinQuad(mb, BuildingSubmeshes.Glass, new Vector3(0, y, hz + 0.03f), Vector3.forward, body.x - 1.2f, 1.7f);
                AddWinQuad(mb, BuildingSubmeshes.Glass, new Vector3(0, y, -hz - 0.03f), Vector3.back, body.x - 1.2f, 1.7f);
                AddWinQuad(mb, BuildingSubmeshes.Glass, new Vector3(hx + 0.03f, y, 0), Vector3.right, body.z - 1.2f, 1.7f);
                AddWinQuad(mb, BuildingSubmeshes.Glass, new Vector3(-hx - 0.03f, y, 0), Vector3.left, body.z - 1.2f, 1.7f);
            }
            // Roof plant boxes.
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(-body.x * 0.2f, h + 0.9f, 0),
                new Vector3(3.2f, 1.4f, 2.6f));
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(body.x * 0.25f, h + 0.7f, body.z * 0.2f),
                new Vector3(2.2f, 1.0f, 2.0f));
        }

        static void BuildRetail(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 5f, 14f);
            var body = BodySize(lot, 0.94f);
            body.y = h;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            FlatRoof(mb, body, h, 0.5f);

            // Ground-floor storefront glass along the facing side.
            float hz = body.z * 0.5f;
            mb.AddBox(BuildingSubmeshes.Glass, new Vector3(0, 1.6f, hz + 0.03f),
                new Vector3(body.x * 0.9f, 2.6f, 0.08f));
            // Canopy strip above the storefront.
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, 3.2f, hz + 0.9f),
                new Vector3(body.x * 0.94f, 0.3f, 1.8f));
            // Upper floors: sparse windows.
            if (h > 6.5f)
                AddWindowGrid(mb, body, h, 3.2f, 1.4f, 1.5f, 3.0f, BuildingSubmeshes.Windows, groundSkip: 3.4f);
            // Rooftop sign block.
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h + 1.0f, 0),
                new Vector3(body.x * 0.5f, 1.2f, 0.5f));
        }

        static void BuildWarehouse(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 6f, 14f);
            var body = BodySize(lot, 0.95f);
            body.y = h;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);

            // Sawtooth roof: repeating north-light ridges along X.
            int teeth = Mathf.Max(2, Mathf.RoundToInt(body.x / 9f));
            float toothW = body.x / teeth;
            for (int i = 0; i < teeth; i++)
            {
                float x = -body.x * 0.5f + toothW * (i + 0.5f);
                mb.AddPyramid(BuildingSubmeshes.Roof, new Vector3(x, h, 0), toothW * 0.5f, 1.6f);
                // Vertical glass strip on each tooth (north light).
                AddWinQuad(mb, BuildingSubmeshes.Glass,
                    new Vector3(x + toothW * 0.25f, h + 0.75f, 0), Vector3.right, body.z * 0.9f, 1.4f);
            }
            // Cargo doors on the facing side.
            float hz = body.z * 0.5f;
            int doors = Mathf.Max(1, Mathf.RoundToInt(body.x / 12f));
            for (int i = 0; i < doors; i++)
            {
                float x = -body.x * 0.5f + body.x * (i + 0.5f) / doors;
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(x, 2.2f, hz + 0.05f),
                    new Vector3(4.2f, 4.4f, 0.14f));
            }
        }

        static void BuildHangar(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 7f, 16f);
            Rect r = lot.rect;
            float w = r.width * 0.95f, d = r.height * 0.95f;

            // Arched profile: stacked boxes of decreasing width (low-poly arch).
            const int steps = 5;
            for (int i = 0; i < steps; i++)
            {
                float t = (float)i / steps;
                float stepW = w * (1f - 0.55f * t * t);
                float stepH = h / steps;
                mb.AddBox(BuildingSubmeshes.Walls,
                    new Vector3(0, stepH * (i + 0.5f), 0),
                    new Vector3(stepW, stepH + 0.02f, d), faces: 0x3F & ~8);
            }
            // Big clear-span door on the facing side.
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h * 0.36f, d * 0.5f + 0.05f),
                new Vector3(w * 0.66f, h * 0.72f, 0.16f));
            // Corner office annex.
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(w * 0.42f, 2f, d * 0.4f),
                new Vector3(4f, 4f, 5f));
        }

        static void BuildStation(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 6f, 12f);
            var body = BodySize(lot, 0.9f);
            body.y = h;
            // Long concourse hall.
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            FlatRoof(mb, body, h, 0.4f);
            // Full-length glass band.
            mb.AddBox(BuildingSubmeshes.Glass, new Vector3(0, h * 0.55f, body.z * 0.5f + 0.03f),
                new Vector3(body.x * 0.88f, h * 0.5f, 0.08f));
            // Elevated platform canopies on slim columns beside the hall.
            float canopyZ = body.z * 0.5f + 3.2f;
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, 5.6f, canopyZ),
                new Vector3(body.x, 0.35f, 4.4f));
            for (float x = -body.x * 0.45f; x <= body.x * 0.45f; x += 6f)
                mb.AddBox(BuildingSubmeshes.Roof, new Vector3(x, 2.8f, canopyZ),
                    new Vector3(0.35f, 5.4f, 0.35f));
            // Clock/sign cube on the roof.
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h + 1.4f, 0),
                new Vector3(1.8f, 1.8f, 1.8f));
        }

        static void BuildControlTower(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Max(lot.height * 1.15f, 14f);
            // Slender shaft.
            mb.AddCylinder(BuildingSubmeshes.Walls, Vector3.zero, 2.1f, h, 8);
            // Observation cab with all-around glass.
            mb.AddCylinder(BuildingSubmeshes.Glass, new Vector3(0, h, 0), 3.4f, 2.4f, 8);
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + 2.55f, 0),
                new Vector3(7.6f, 0.4f, 7.6f));
            mb.AddPyramid(BuildingSubmeshes.Roof, new Vector3(0, h + 2.75f, 0), 3.6f, 1.6f);
            // Antenna.
            mb.AddCylinder(BuildingSubmeshes.Accent, new Vector3(0, h + 4.3f, 0), 0.08f, 3.2f, 6);
            // Base building.
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(3.8f, 1.6f, 0), new Vector3(6f, 3.2f, 5f));
        }

        static void BuildSilo(MeshBuilder mb, LotData lot)
        {
            Rect r = lot.rect;
            float h = Mathf.Clamp(lot.height, 8f, 22f);
            // Cluster of cylindrical tanks (2x2 or 3x2 depending on lot width).
            int cols = r.width > 22f ? 3 : 2;
            int rows = 2;
            float radius = Mathf.Min(r.width / (cols * 2.4f), r.height / (rows * 2.4f), 4.5f);
            for (int i = 0; i < cols; i++)
            for (int j = 0; j < rows; j++)
            {
                float x = (i - (cols - 1) * 0.5f) * radius * 2.4f;
                float z = (j - (rows - 1) * 0.5f) * radius * 2.4f;
                float tankH = h * (0.85f + 0.15f * ((i + j) % 2));
                mb.AddCylinder(BuildingSubmeshes.Accent, new Vector3(x, 0, z), radius, tankH, 10);
                mb.AddPyramid(BuildingSubmeshes.Roof, new Vector3(x, tankH, z), radius, radius * 0.7f);
            }
            // Piping bridge.
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h * 0.6f, 0),
                new Vector3(r.width * 0.7f, 0.5f, 1.2f));
        }

        static void BuildTerminal(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 7f, 15f);
            var body = BodySize(lot, 0.96f);
            body.y = h;
            // Wide slab.
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body, faces: 0x3F & ~8);
            FlatRoof(mb, body, h, 0.6f);
            // Full-width glass departure band.
            mb.AddBox(BuildingSubmeshes.Glass, new Vector3(0, h * 0.62f, body.z * 0.5f + 0.03f),
                new Vector3(body.x * 0.92f, h * 0.42f, 0.08f));
            // Signage crown.
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h + 1.2f, 0),
                new Vector3(body.x * 0.4f, 1.4f, 0.6f));
            // Fingers / jet-bridge stubs on the facing side.
            int fingers = Mathf.Max(1, Mathf.RoundToInt(body.x / 18f));
            for (int i = 0; i < fingers; i++)
            {
                float x = -body.x * 0.5f + body.x * (i + 0.5f) / fingers;
                mb.AddBox(BuildingSubmeshes.Walls, new Vector3(x, 2.2f, body.z * 0.5f + 4.5f),
                    new Vector3(3f, 3.4f, 9f));
                mb.AddBox(BuildingSubmeshes.Glass, new Vector3(x, 3.4f, body.z * 0.5f + 8.4f),
                    new Vector3(2.4f, 1.4f, 1.2f));
            }
        }

        static void BuildMetroTower(MeshBuilder mb, LotData lot)
        {
            var footprint = BodySize(lot, 0.94f);
            float h = Mathf.Max(18f, lot.height);
            float podiumH = Mathf.Min(6f, h * 0.2f);
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, podiumH * 0.5f, 0),
                new Vector3(footprint.x, podiumH, footprint.z));
            AddWindowGrid(mb, new Vector3(footprint.x, podiumH, footprint.z), podiumH,
                2.8f, 1.7f, 1.5f, 3.2f, BuildingSubmeshes.Glass);

            float towerW = footprint.x * 0.58f, towerD = footprint.z * 0.7f;
            float towerH = h - podiumH;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, podiumH + towerH * 0.5f, 0),
                new Vector3(towerW, towerH, towerD));
            for (float y = podiumH + 2f; y < h - 1f; y += 3.4f)
                mb.AddBox(BuildingSubmeshes.Glass, new Vector3(0, y, towerD * 0.5f + 0.04f),
                    new Vector3(towerW * 0.82f, 1.65f, 0.1f));
            for (float x = -towerW * 0.5f; x <= towerW * 0.5f; x += Mathf.Max(3.5f, towerW * 0.36f))
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(x, podiumH + towerH * 0.5f, towerD * 0.5f + 0.15f),
                    new Vector3(0.45f, towerH, 0.35f));
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + 0.7f, 0),
                new Vector3(towerW + 2f, 1.4f, towerD + 2f));
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h + 1.8f, 0),
                new Vector3(towerW * 0.32f, 1.1f, towerD * 0.32f));
        }

        static void BuildMetroStation(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 5f, 13f);
            var body = BodySize(lot, 0.96f);
            body.y = h;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body);
            mb.AddBox(BuildingSubmeshes.Glass, new Vector3(0, h * 0.52f, body.z * 0.5f + 0.04f),
                new Vector3(body.x * 0.88f, h * 0.55f, 0.1f));
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + 0.45f, 0),
                new Vector3(body.x + 1.2f, 0.9f, body.z + 1.2f));

            float stairZ = body.z * 0.5f + 4f;
            for (int side = -1; side <= 1; side += 2)
            {
                float x = side * body.x * 0.27f;
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(x, 1.3f, stairZ),
                    new Vector3(body.x * 0.24f, 2.6f, 7f));
                mb.AddBox(BuildingSubmeshes.Glass, new Vector3(x, 2.8f, stairZ + 3.3f),
                    new Vector3(body.x * 0.26f, 0.45f, 0.6f));
            }
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h + 1.4f, 0),
                new Vector3(body.x * 0.62f, 1f, 1.2f));
        }

        static void BuildRailDepot(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 8f, 20f);
            var body = BodySize(lot, 0.97f);
            body.y = h;
            float roofH = Mathf.Clamp(body.z * 0.18f, 2f, 5f);
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body);

            float x = body.x * 0.5f, z = body.z * 0.5f;
            // Gabled roof profile and end walls make this read as a train shed.
            mb.AddQuad(BuildingSubmeshes.Roof, new Vector3(-x, h, -z), new Vector3(-x, h, z),
                new Vector3(0, h + roofH, z), new Vector3(0, h + roofH, -z), Vector3.left);
            mb.AddQuad(BuildingSubmeshes.Roof, new Vector3(0, h + roofH, -z), new Vector3(0, h + roofH, z),
                new Vector3(x, h, z), new Vector3(x, h, -z), Vector3.right);
            mb.AddTri(BuildingSubmeshes.Roof, new Vector3(-x, h, z), new Vector3(x, h, z), new Vector3(0, h + roofH, z));
            mb.AddTri(BuildingSubmeshes.Roof, new Vector3(x, h, -z), new Vector3(-x, h, -z), new Vector3(0, h + roofH, -z));

            int bays = Mathf.Max(2, Mathf.FloorToInt(body.x / 7f));
            for (int bay = 0; bay < bays; bay++)
            {
                float doorX = -x + body.x * (bay + 0.5f) / bays;
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(doorX, h * 0.36f, z + 0.08f),
                    new Vector3(body.x / bays * 0.72f, h * 0.68f, 0.16f));
                mb.AddBox(BuildingSubmeshes.Glass, new Vector3(doorX, h * 0.86f, z + 0.1f),
                    new Vector3(body.x / bays * 0.58f, 1.1f, 0.12f));
            }
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + roofH + 0.8f, 0),
                new Vector3(body.x * 0.6f, 1f, 1.5f));
        }

        static void BuildHarborWarehouse(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height, 7f, 16f);
            var body = BodySize(lot, 0.97f);
            body.y = h;
            mb.AddBox(BuildingSubmeshes.Walls, new Vector3(0, h * 0.5f, 0), body);
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + 0.8f, 0),
                new Vector3(body.x + 1f, 1.6f, body.z + 1f));
            AddWindowGrid(mb, body, h, 4f, 2.8f, 1.4f, 5f, BuildingSubmeshes.Glass, groundSkip: 2.2f);

            float frontZ = body.z * 0.5f + 0.12f;
            int doors = Mathf.Max(2, Mathf.FloorToInt(body.x / 7f));
            for (int i = 0; i < doors; i++)
            {
                float doorX = -body.x * 0.5f + body.x * (i + 0.5f) / doors;
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(doorX, 2.5f, frontZ),
                    new Vector3(body.x / doors * 0.7f, 5f, 0.2f));
                if ((i & 1) == 0)
                    mb.AddBox(BuildingSubmeshes.Roof, new Vector3(doorX, 5.1f, frontZ + 1.9f),
                        new Vector3(body.x / doors * 0.95f, 0.3f, 3.8f));
            }

            // Short container stacks mark the yard-facing side of the shed.
            float sideX = body.x * 0.5f + 1.4f;
            for (int tier = 0; tier < 2; tier++)
                mb.AddBox(BuildingSubmeshes.Accent, new Vector3(sideX, 1.5f + tier * 3f, 0),
                    new Vector3(2.5f, 2.8f, body.z * (tier == 0 ? 0.7f : 0.52f)));
        }

        static void BuildHarborSilo(MeshBuilder mb, LotData lot)
        {
            BuildSilo(mb, lot);
            Rect r = lot.rect;
            float h = Mathf.Clamp(lot.height, 8f, 22f);
            float radius = Mathf.Min(r.width / 7f, r.height / 5f, 4f);
            for (int i = -1; i <= 1; i++)
            {
                float x = i * radius * 2.2f;
                mb.AddBox(BuildingSubmeshes.Glass, new Vector3(x, h * 0.62f, radius * 2.6f),
                    new Vector3(0.9f, 0.45f, radius * 1.5f));
            }
            mb.AddBox(BuildingSubmeshes.Accent, new Vector3(0, h * 0.74f, 0),
                new Vector3(r.width * 0.78f, 0.55f, 0.7f));
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, 1.2f, -r.height * 0.36f),
                new Vector3(r.width * 0.72f, 1.6f, 1.2f));
        }

        static void BuildLighthouse(MeshBuilder mb, LotData lot)
        {
            float h = Mathf.Clamp(lot.height * 1.2f, 18f, 36f);
            float radius = Mathf.Clamp(Mathf.Min(lot.rect.width, lot.rect.height) * 0.14f, 2f, 4.2f);
            mb.AddCylinder(BuildingSubmeshes.Walls, Vector3.zero, radius * 1.45f, h * 0.32f, 10);
            mb.AddCylinder(BuildingSubmeshes.Accent, new Vector3(0, h * 0.32f, 0), radius,
                h * 0.55f, 10);
            mb.AddCylinder(BuildingSubmeshes.Walls, new Vector3(0, h * 0.87f, 0), radius * 1.05f,
                h * 0.1f, 10);
            mb.AddCylinder(BuildingSubmeshes.Glass, new Vector3(0, h * 0.97f, 0), radius * 1.55f,
                2.4f, 10);
            mb.AddBox(BuildingSubmeshes.Roof, new Vector3(0, h + 2.8f, 0),
                new Vector3(radius * 3.5f, 0.5f, radius * 3.5f));
            mb.AddPyramid(BuildingSubmeshes.Accent, new Vector3(0, h + 3f, 0), radius * 1.8f, 2.8f);
            mb.AddCylinder(BuildingSubmeshes.Accent, new Vector3(0, h + 5.8f, 0), 0.08f, 2.4f, 6);
        }
    }
}
