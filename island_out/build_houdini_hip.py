"""Run this file inside Houdini to create and save a native .hip scene."""
import os
import hou

OUTPUT_DIR = r"C:/Users/bnna7/workspace/Houdini/island_out"
OBJ_PATH = os.path.join(OUTPUT_DIR, "island_houdini_scene.obj")
HIP_PATH = os.path.join(OUTPUT_DIR, "Island_20261002.hip")

if not os.path.isfile(OBJ_PATH):
    raise RuntimeError("Island OBJ not found: " + OBJ_PATH)

obj = hou.node("/obj")
island_geo = obj.createNode("geo", "Island_Scene")
for child in island_geo.children():
    child.destroy()
file_sop = island_geo.createNode("file", "Island_Geometry")
file_sop.parm("file").set(OBJ_PATH)
file_sop.setDisplayFlag(True)
file_sop.setRenderFlag(True)
file_sop.setSelected(True, clear_all_selected=True)
island_geo.layoutChildren()

camera = obj.createNode("cam", "Island_Camera")
camera.parmTuple("t").set((0.0, 1200.0, -2000.0))
camera.parmTuple("r").set((-31.0, 0.0, 0.0))
camera.parm("focal").set(50.0)
obj.layoutChildren()

hou.hipFile.save(HIP_PATH)
print("Saved native Houdini island scene: " + HIP_PATH)
