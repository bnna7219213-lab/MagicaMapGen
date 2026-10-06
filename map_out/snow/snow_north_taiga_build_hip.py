"""Run inside Houdini's Python Source Editor to save a .hip."""
import os
import hou

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OBJ_PATH = os.path.join(OUTPUT_DIR, "snow_north_taiga_scene.obj")
HIP_PATH = os.path.join(OUTPUT_DIR, "snow_north_taiga_scene.hip")

if not os.path.isfile(OBJ_PATH):
    raise RuntimeError("OBJ not found: " + OBJ_PATH)

obj_node = hou.node("/obj")
geo = obj_node.createNode("geo", "雪地_Scene")
for child in geo.children():
    child.destroy()
file_sop = geo.createNode("file", "Map_Geometry")
file_sop.parm("file").set(OBJ_PATH)
file_sop.setDisplayFlag(True)
file_sop.setRenderFlag(True)
geo.layoutChildren()

cam = obj_node.createNode("cam", "Overview_Camera")
cam.parmTuple("t").set((0.0, 1200.0, -2000.0))
cam.parmTuple("r").set((-31.0, 0.0, 0.0))
cam.parm("focal").set(50.0)
obj_node.layoutChildren()

hou.hipFile.save(HIP_PATH)
print("Saved: " + HIP_PATH)
