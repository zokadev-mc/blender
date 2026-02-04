# PARTE 1/4 - hytaleModdingTools.py
# CAMBIOS RECIENTES

# fixed version of HytaleModelExporterPre.py
# Changes:
# - v0.33: "Safety Check" Popup on Export.
# - v0.34: Compact JSON formatting.
# - v0.35: Math fix logic.
# - v0.36: Attempted bpy.ops (Context sensitive).
# - v0.37: MATRIX MATH FIX (Hard). Se aplica manualmente la multiplicación de matrices
#          (ParentInverse @ Local) para garantizar que el "Apply Parent Inverse" ocurra
#          sin depender del contexto visual o selección de Blender.

bl_info = {
    "name": "Hytale Model Tools (Import/Export)",
    "author": "Jarvis",
    "version": (0, 38),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Hytale",
    "description": "Exportador v0.37 (Matrix Math Hard Fix).",
    "category": "Import-Export",
}

import bpy
import json
import mathutils
import re
import os
import math
import bmesh
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras.io_utils import ImportHelper

# --- CONSTANTES ---
FIXED_GLOBAL_SCALE = 16.0
RESERVED_NAMES = {} 

# --- UTILIDADES GENERALES ---

def standard_round(n):
    return int(math.floor(n + 0.5))

def get_image_size_from_objects(objects):
    for obj in objects:
        if obj.type == 'MESH' and obj.active_material and obj.active_material.use_nodes:
            for node in obj.active_material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    return node.image.size[0], node.image.size[1]
    return None, None

# --- LÓGICA DE INTERFAZ Y VALIDACIÓN ---

def update_hytale_grid_setup(self, context):
    """
    Configura el entorno Hytale usando la API descubierta (space.uv_editor).
    """
    # 1. Ajuste de Unidades (Global)
    if self.setup_pixel_grid:
        context.scene.unit_settings.system = 'NONE'
    else:
        context.scene.unit_settings.system = 'METRIC'
        self.show_subdivisions = False

    # 2. Configurar VIEW_3D (Grid del suelo)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        if self.setup_pixel_grid:
                            space.overlay.grid_scale = 1
                            space.overlay.grid_subdivisions = 16
                            space.overlay.show_floor = True
                        else:
                            space.overlay.grid_scale = 1.0
                            space.overlay.grid_subdivisions = 10

    # 3. [CORREGIDO] Configurar UV EDITOR con la API 'space.uv_editor'
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            # Buscamos por ui_type='UV' para dar con el editor correcto
            if area.ui_type == 'UV': 
                area.tag_redraw()
                for space in area.spaces:
                    if space.type == 'IMAGE_EDITOR':
                        # Verificamos si existe el sub-objeto que encontraste en el log
                        if hasattr(space, 'uv_editor'):
                            uv_settings = space.uv_editor
                            
                            if self.setup_pixel_grid:
                                # --- ACTIVAR MODO PIXEL PERFECT ---
                                
                                # 1. Ver las caras (malla rellena)
                                uv_settings.show_faces = True 
                                
                                # 2. Activar la rejilla sobre la imagen
                                uv_settings.show_grid_over_image = True
                                
                                
                                # 3. Configurar la fuente de la rejilla a PIXELES
                                # (Esto sustituye al antiguo show_pixel_grid)
                                try:
                                    uv_settings.grid_shape_source = 'PIXEL'
                                except Exception:
                                    # Si 'PIXEL' falla, probamos 'DYNAMIC' o lo dejamos estar
                                    pass
                                
                                # 4. Desactivar distorsión
                                uv_settings.show_stretch = False
                                
                            else:
                                # --- DESACTIVAR ---
                                uv_settings.show_grid_over_image = False
                                # Opcional: apagar caras
                                # uv_settings.show_faces = False
                                
                        if hasattr(space, 'overlay'):
                            uv_settings2 = space.overlay

                            if self.setup_pixel_grid:
                                # --- ACTIVAR MODO PIXEL PERFECT ---
                                try:
                                    # 1. Ver las caras (malla rellena)
                                    uv_settings2.show_overlays = True 
                                
                                    # 2. Activar la rejilla sobre la imagen
                                    uv_settings2.show_grid_background = True
                                
                                except Exception:
                                    pass
                                
                            else:
                                # --- DESACTIVAR ---
                                uv_settings2.show_grid_background = False
                                uv_settings.show_grid_over_image = False

def update_grid_subdivisions(self, context):
    """Lógica relativa: Divide o multiplica la escala actual por 16"""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    curr = space.overlay.grid_scale
                    if self.show_subdivisions:
                        space.overlay.grid_scale = curr / 16.0
                    else:
                        space.overlay.grid_scale = curr * 16.0

def draw_validator_ui(self, context, layout):
    """Función que escanea la colección y muestra advertencias en tiempo real"""
    props = context.scene.hytale_props
    collection = props.target_collection 
    
    if not collection:
        box = layout.box()
        box.label(text="¡Selecciona una Colección!", icon='ERROR')
        return
    issues_found = False
    
    box = layout.box()
    box.label(text="Diagnóstico en Tiempo Real:", icon='VIEWZOOM')
    
    complex_objs = []
    negative_scale_objs = []
    no_mat_objs = []
    mesh_parent_mesh_objs = []
    
    for obj in collection.objects:
        if obj.type == 'MESH':
            # Checks
            if obj.scale.x < 0 or obj.scale.y < 0 or obj.scale.z < 0: negative_scale_objs.append(obj.name)
            if not obj.data.materials: no_mat_objs.append(obj.name)
            if len(obj.data.vertices) > 8: complex_objs.append(obj.name)
            if obj.parent and obj.parent.type == 'MESH': mesh_parent_mesh_objs.append(obj.name)

    # Siblings check
    siblings_issue = False
    parent_map = {}
    for obj in collection.objects:
        if obj.parent and obj.type == 'MESH':
            if obj.parent.type != 'MESH':
                if obj.parent.name not in parent_map: parent_map[obj.parent.name] = 0
                parent_map[obj.parent.name] += 1
                if parent_map[obj.parent.name] > 1: siblings_issue = True

    # Render
    if complex_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True 
        col.label(text="Geometría Compleja (ERROR):", icon='CANCEL')
        col.label(text="(Modelo con vertices > 8 detectado.)", icon='BLANK1')
        for name in complex_objs[:5]: col.label(text=f"• {name}", icon='MESH_DATA')
        col.separator()

    if mesh_parent_mesh_objs:
        issues_found = True
        col = box.column(align=True)
        col.label(text="ADVERTENCIA: Malla dentro de Malla", icon='ERROR') 
        col.label(text="ACCIÓN: Se romperá el parentesco al exportar.", icon='UNLINKED')
        for name in mesh_parent_mesh_objs[:3]:
            col.label(text=f"• {name} -> Se soltará")
        col.separator()

    if negative_scale_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True
        col.label(text="Escala Negativa (Caras invertidas):", icon='ERROR')
        for name in negative_scale_objs[:3]: col.label(text=f"• {name}")
        col.separator()

    if no_mat_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True
        col.label(text="Falta Material/Textura:", icon='MATERIAL')
        for name in no_mat_objs[:3]: col.label(text=f"• {name}")
        col.separator()

    if siblings_issue:
        issues_found = False
        col = box.column(align=True)
        col.label(text="Jerarquía Múltiple (Empties)", icon='INFO')
        col.label(text="Se crearán Wrappers individuales.", icon='CHECKMARK')

    if not issues_found:
        row = box.row()
        row.label(text="Estado: Todo Correcto", icon='FILE_TICK')

# --- LÓGICA DE REFERENCIAS ---

def get_templates_path():
    addon_dir = os.path.dirname(__file__)
    return os.path.join(addon_dir, "templates")

def get_templates_list(self, context):
    path = get_templates_path()
    items = []
    if os.path.exists(path) and os.path.isdir(path):
        for f in os.listdir(path):
            if f.lower().endswith(".blend"):
                display_name = os.path.splitext(f)[0]
                items.append((f, display_name, f"Cargar {display_name}"))
    if not items:
        items.append(('NONE', "Sin referencias", "Carpeta 'templates' vacía"))
    return items

# --- LÓGICA DE EXPORTACIÓN OPTIMIZADA ---

def clean_num(n):
    """Si el número es 2.0 devuelve 2, si es 2.5 devuelve 2.5"""
    n = round(n, 4) # Mantenemos 4 decimales de precisión
    return int(n) if n.is_integer() else n

def blender_to_hytale_pos(vec):
    x = vec.x * FIXED_GLOBAL_SCALE
    y = vec.z * FIXED_GLOBAL_SCALE 
    z = -vec.y * FIXED_GLOBAL_SCALE 
    # Usamos clean_num en lugar de solo round
    return {"x": clean_num(x), "y": clean_num(y), "z": clean_num(z)}

def blender_to_hytale_quat(quat):
    # Los cuaterniones son sensibles, usamos 5 decimales pero limpiamos ceros
    return {
        "x": clean_num(quat.x), 
        "y": clean_num(quat.z), 
        "z": clean_num(-quat.y), 
        "w": clean_num(quat.w)
    }

def get_face_name_dominant(normal):
    x, y, z = normal.x, normal.y, normal.z
    abs_x, abs_y, abs_z = abs(x), abs(y), abs(z)
    if abs_z >= abs_x and abs_z >= abs_y:
        return "top" if z > 0 else "bottom"
    elif abs_y >= abs_x and abs_y >= abs_z:
        return "back" if y > 0 else "front"
    else:
        return "right" if x > 0 else "left"

def extract_uvs(obj, output_w, output_h, snap_to_pixels):
    uv_layout = {} 
    
    if not obj.data.uv_layers.active:
        return uv_layout

    mesh = obj.data
    uv_layer = mesh.uv_layers.active.data
    scale = obj.scale
    
    for poly in mesh.polygons:
        face_name = get_face_name_dominant(poly.normal)
        
        raw_uvs = [uv_layer[loop_idx].uv for loop_idx in poly.loop_indices]
        if not raw_uvs: continue

        min_u = min(uv.x for uv in raw_uvs)
        max_u = max(uv.x for uv in raw_uvs)
        min_v = min(uv.y for uv in raw_uvs)
        max_v = max(uv.y for uv in raw_uvs)
        
        x_start_f = min_u * output_w
        x_end_f = max_u * output_w
        y_top_f = (1.0 - max_v) * output_h
        y_bottom_f = (1.0 - min_v) * output_h

        if snap_to_pixels:
            x_left = standard_round(x_start_f)
            x_right = standard_round(x_end_f)
            y_top = standard_round(y_top_f)
            y_bottom = standard_round(y_bottom_f)
        else:
            x_left = x_start_f
            x_right = x_end_f
            y_top = y_top_f
            y_bottom = y_bottom_f
            
        uv_pixel_width = abs(x_right - x_left)
        uv_pixel_height = abs(y_bottom - y_top)
        uv_is_vertical = uv_pixel_height > uv_pixel_width

        verts = [mesh.vertices[idx].co for idx in poly.vertices]
        scaled_verts = [mathutils.Vector((v.x * abs(scale.x), v.y * abs(scale.y), v.z * abs(scale.z))) for v in verts]
        
        face_width_3d = 0.0
        face_height_3d = 0.0
        
        if face_name in ['front', 'back']: 
            face_width_3d = max(v.x for v in scaled_verts) - min(v.x for v in scaled_verts)
            face_height_3d = max(v.z for v in scaled_verts) - min(v.z for v in scaled_verts)
        elif face_name in ['left', 'right']: 
            face_width_3d = max(v.y for v in scaled_verts) - min(v.y for v in scaled_verts)
            face_height_3d = max(v.z for v in scaled_verts) - min(v.z for v in scaled_verts)
        else: 
            face_width_3d = max(v.x for v in scaled_verts) - min(v.x for v in scaled_verts)
            face_height_3d = max(v.y for v in scaled_verts) - min(v.y for v in scaled_verts)
            
        face_is_vertical = face_height_3d > face_width_3d
        
        angle = 0
        if (face_is_vertical != uv_is_vertical) and (abs(face_width_3d - face_height_3d) > 0.01):
            if face_name in ['right', 'left']:
                angle = 270 
            else:
                uv0 = uv_layer[poly.loop_indices[0]].uv
                uv1 = uv_layer[poly.loop_indices[1]].uv
                du = uv1.x - uv0.x
                v0 = scaled_verts[0]
                v1 = scaled_verts[1]
                d_vert_3d = (v1.z - v0.z) if face_name in ['front', 'back'] else (v1.y - v0.y)
                angle = 270 if (du > 0) == (d_vert_3d > 0) else 90
        
        final_offset_x = x_left
        final_offset_y = y_top
        
        if angle == 270: 
            final_offset_x = x_left
            final_offset_y = y_bottom
        elif angle == 90:
            final_offset_x = x_right
            final_offset_y = y_top
        elif angle == 180:
            final_offset_x = x_right
            final_offset_y = y_bottom
            
        uv_layout[face_name] = {
            "offset": {"x": int(final_offset_x), "y": int(final_offset_y)},
            "mirror": {"x": False, "y": False},
            "angle": int(angle)
        }
    return uv_layout

def process_node(obj, out_w, out_h, snap_uvs, id_counter):
    # --- PROCESO TRAS APLICAR INVERSO ---
    # Gracias a la matemática aplicada en la colección temporal, 
    # obj.matrix_local ya contiene la transformación relativa limpia.
    
    loc, rot, sca = obj.matrix_local.decompose()
    
    local_center = mathutils.Vector((0,0,0))
    final_dims = mathutils.Vector((0,0,0))
    has_geometry = False

    if obj.type == 'MESH' and len(obj.data.vertices) > 0:
        verts = [v.co for v in obj.data.vertices]
        min_v = mathutils.Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
        max_v = mathutils.Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
        
        # Para la geometría (Bounds), seguimos usando la escala del bloque de datos
        scale_data = obj.scale 
        real_min = mathutils.Vector((min_v.x * scale_data.x, min_v.y * scale_data.y, min_v.z * scale_data.z))
        real_max = mathutils.Vector((max_v.x * scale_data.x, max_v.y * scale_data.y, max_v.z * scale_data.z))
        
        local_center = (real_min + real_max) / 2.0
        final_dims = mathutils.Vector((abs(real_max.x - real_min.x), abs(real_max.y - real_min.y), abs(real_max.z - real_min.z)))
        has_geometry = True

    final_name = obj.name
    if final_name in RESERVED_NAMES:
        final_name = final_name + "_Geo"

    node_data = {
        "id": str(id_counter[0]),
        "name": final_name,
        "position": blender_to_hytale_pos(loc),      
        "orientation": blender_to_hytale_quat(rot),  
        "children": [],
        "shape": {"type": "none"} 
    }
    id_counter[0] += 1

    def get_hytale_size(val, do_snap):
        scaled = val * FIXED_GLOBAL_SCALE
        if do_snap:
            return int(round(scaled))
        return round(scaled, 4)

    if has_geometry:
        is_plane = (final_dims.x < 0.001) or (final_dims.y < 0.001) or (final_dims.z < 0.001)
        
        shape_offset = blender_to_hytale_pos(local_center)
        texture_layout = extract_uvs(obj, out_w, out_h, snap_to_pixels=snap_uvs)

        hytale_normal = None
        if is_plane:
            if final_dims.x < 0.001: 
                hytale_normal = "+X"
                filtered_size = {
                    "x": get_hytale_size(final_dims.y, snap_uvs), 
                    "y": get_hytale_size(final_dims.z, snap_uvs)
                }
            elif final_dims.z < 0.001: 
                hytale_normal = "+Y"
                filtered_size = {
                    "x": get_hytale_size(final_dims.x, snap_uvs), 
                    "y": get_hytale_size(final_dims.y, snap_uvs)
                }
            else: 
                hytale_normal = "+Z"
                filtered_size = {
                    "x": get_hytale_size(final_dims.x, snap_uvs), 
                    "y": get_hytale_size(final_dims.z, snap_uvs)
                }
            
            valid_face = None
            for k, v in texture_layout.items():
                if v["offset"]["x"] != 0 or v["offset"]["y"] != 0 or v["angle"] != 0:
                    valid_face = v
                    break
            if not valid_face and texture_layout:
                valid_face = list(texture_layout.values())[0]
            
            texture_layout = {"front": valid_face} if valid_face else {}
        else:
            full_size = {
                "x": get_hytale_size(final_dims.x, snap_uvs), 
                "y": get_hytale_size(final_dims.z, snap_uvs), 
                "z": get_hytale_size(final_dims.y, snap_uvs)
            }
            filtered_size = {k: v for k, v in full_size.items() if v != 0}
            
            clean_layout = {}
            for k, v in texture_layout.items():
                clean_layout[k] = v
            texture_layout = clean_layout

        node_data["shape"] = {
            "type": "quad" if is_plane else "box",
            "offset": shape_offset,
            "textureLayout": texture_layout,
            "unwrapMode": "custom",
            "settings": {
                "isPiece": False,
                "size": filtered_size,
                "isStaticBox": True
            },
            "doubleSided": is_plane,
            "shadingMode": "flat"
        }
        if hytale_normal: node_data["shape"]["settings"]["normal"] = hytale_normal

    for child in obj.children:
        node_data["children"].append(process_node(child, out_w, out_h, snap_uvs, id_counter))

    # --- NUEVO: SI NO TIENE HIJOS, BORRAMOS LA CLAVE ---
    if not node_data["children"]:
        del node_data["children"]
    # ---------------------------------------------------
    
    return node_data

# ==========================================
#       LÓGICA DE RECONSTRUCCIÓN (ROT)
# ==========================================

def reconstruct_orientation_from_geometry(obj):
    """
    Intenta alinear la geometría interna a los ejes globales y transferir
    la rotación al objeto (transform). Vital para objetos con 'Apply Transforms'.
    Fix v24.17: Soporte para Quads usando vectores de arista si falta una 2da cara.
    """
    if obj.type != 'MESH': return
