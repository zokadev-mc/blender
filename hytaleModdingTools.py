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
        
def get_face_basis_vectors(normal):
    """Retorna vectores (Right, Up) para una normal dada según el estándar Hytale/Blockbench"""
    epsilon = 0.9
    if normal.z > epsilon:    # TOP
        return mathutils.Vector((1, 0, 0)), mathutils.Vector((0, 1, 0))
    elif normal.z < -epsilon: # BOTTOM
        return mathutils.Vector((1, 0, 0)), mathutils.Vector((0, -1, 0))
    elif normal.y > epsilon:  # BACK
        return mathutils.Vector((-1, 0, 0)), mathutils.Vector((0, 0, 1))
    elif normal.y < -epsilon: # FRONT
        return mathutils.Vector((1, 0, 0)), mathutils.Vector((0, 0, 1))
    elif normal.x > epsilon:  # RIGHT
        return mathutils.Vector((0, 1, 0)), mathutils.Vector((0, 0, 1))
    elif normal.x < -epsilon: # LEFT
        return mathutils.Vector((0, -1, 0)), mathutils.Vector((0, 0, 1))
    else:
        up = mathutils.Vector((0, 0, 1))
        right = up.cross(normal)
        return right, up

def extract_uvs(obj, output_w, output_h, snap_to_pixels):
    uv_layout = {} 
    
    if not obj.data.uv_layers.active:
        return uv_layout

    mesh = obj.data
    uv_layer = mesh.uv_layers.active.data
    
    for poly in mesh.polygons:
        # 1. Determinar orientación 3D
        face_name = get_face_name_dominant(poly.normal)
        ref_right, ref_up = get_face_basis_vectors(poly.normal)
        
        # 2. Obtener UVs y Vértices
        loops = [uv_layer[i] for i in poly.loop_indices]
        verts = [mesh.vertices[i].co for i in poly.vertices]
        
        if not loops or not verts:
            continue

        # 3. Calcular Bounding Box UV VISUAL (Blender Space)
        us = [l.uv.x for l in loops]
        vs = [l.uv.y for l in loops]
        min_u, max_u = min(us), max(us)
        min_v, max_v = min(vs), max(vs)
        
        # Convertir a Píxeles (Top-Left Origin para cálculos lógicos)
        x_left = min_u * output_w
        x_right = max_u * output_w
        # Invertimos Y porque Blender es Bottom-Left y Hytale/Imágenes son Top-Left
        y_top = (1.0 - max_v) * output_h
        y_bottom = (1.0 - min_v) * output_h

        if snap_to_pixels:
            x_left, x_right = standard_round(x_left), standard_round(x_right)
            y_top, y_bottom = standard_round(y_top), standard_round(y_bottom)
        
        width_px = abs(x_right - x_left)
        height_px = abs(y_bottom - y_top)

        # ------------------------------------------------------------
        # 4. DETECCIÓN DE ROTACIÓN (definir angle) - heurística original
        # ------------------------------------------------------------
        # Evitamos NameError asegurando que 'angle' siempre exista.
        angle = 0
        try:
            v0, v1 = verts[0], verts[1]
            uv0, uv1 = loops[0].uv, loops[1].uv

            d_3d = v1 - v0
            d_uv = uv1 - uv0

            dx_3d = d_3d.dot(ref_right)
            dy_3d = d_3d.dot(ref_up)

            # Tolerancia para evitar falsos positivos (FIX v0.39)
            EPS = 0.0001

            # Detectar ángulo basándonos en si el borde horizontal 3D se mueve en U o V
            if abs(dx_3d) > abs(dy_3d):
                if abs(d_uv.y) > abs(d_uv.x) + EPS:
                    angle = 90
            else:
                if abs(d_uv.x) > abs(d_uv.y) + EPS:
                    angle = 90
        except Exception:
            # en caso de cualquier problema, mantenemos angle = 0
            angle = 0

        # ------------------------------------------------------------
        # 4b. DETECCIÓN DE ESPEJO (Robusta via Jacobiana)
        # ------------------------------------------------------------
        # Calculamos una aproximación lineal que mapea (lx,ly) -> (uv.x, uv.y)
        # y usamos su determinante y signos para detectar mirror/flip por eje.

        EPS_J = 1e-8

        # Proyección geométrica para encontrar coordenadas locales (lx,ly) y UVs
        proj_verts = []
        for i, v in enumerate(verts):
            lx = (v - poly.center).dot(ref_right)
            ly = (v - poly.center).dot(ref_up)
            proj_verts.append({'lx': lx, 'ly': ly, 'uv': loops[i].uv})

        n = len(proj_verts)
        visual_mirror_u = False
        visual_mirror_v = False

        if n < 3:
            # fallback simple si no hay suficientes puntos
            left_v = min(proj_verts, key=lambda p: p['lx'])
            right_v = max(proj_verts, key=lambda p: p['lx'])
            bottom_v = min(proj_verts, key=lambda p: p['ly'])
            top_v = max(proj_verts, key=lambda p: p['ly'])

            visual_mirror_u = (left_v['uv'].x > right_v['uv'].x + 1e-6)
            visual_mirror_v = (bottom_v['uv'].y > top_v['uv'].y + 1e-6)
        else:
            mean_lx = sum(p['lx'] for p in proj_verts) / n
            mean_ly = sum(p['ly'] for p in proj_verts) / n
            mean_uvx = sum(p['uv'].x for p in proj_verts) / n
            mean_uvy = sum(p['uv'].y for p in proj_verts) / n

            # construir sums para resolución 2x2 (A^T A) y A^T B
            Sxx = Sxy = Syy = 0.0
            Sxux = Syux = 0.0
            Sxuy = Syuy = 0.0

            for p in proj_verts:
                cx = p['lx'] - mean_lx
                cy = p['ly'] - mean_ly
                ux = p['uv'].x - mean_uvx
                uy = p['uv'].y - mean_uvy

                Sxx += cx * cx
                Sxy += cx * cy
                Syy += cy * cy

                Sxux += cx * ux
                Syux += cy * ux

                Sxuy += cx * uy
                Syuy += cy * uy

            det_mat = (Sxx * Syy - Sxy * Sxy)

            if abs(det_mat) > EPS_J:
                # resolver para coeficientes que mapean (lx,ly) -> uv.x
                a_u = (Sxux * Syy - Syux * Sxy) / det_mat
                b_u = (Syux * Sxx - Sxux * Sxy) / det_mat

                # y para uv.y
                a_v = (Sxuy * Syy - Syuy * Sxy) / det_mat
                b_v = (Syuy * Sxx - Sxuy * Sxy) / det_mat

                # Jacobiana 2x2: [[a_u, b_u], [a_v, b_v]]
                detJ = (a_u * b_v - b_u * a_v)

                # visual_mirror_u: al movernos hacia la derecha en 3D (lx aumenta),
                # ¿disminuye U? => mirror horizontal visual
                visual_mirror_u = (a_u < -EPS_J)
                # visual_mirror_v: al movernos hacia arriba en 3D (ly aumenta),
                # ¿disminuye V? => mirror vertical visual
                visual_mirror_v = (b_v < -EPS_J)

                # Si la matriz tiene determinante negativo => inversión global detectable.
                if detJ < 0 and not (visual_mirror_u or visual_mirror_v):
                    # elegimos el eje con mayor influencia absoluta (heurística)
                    influence_u = abs(a_u) + abs(b_u)
                    influence_v = abs(a_v) + abs(b_v)
                    if influence_u >= influence_v:
                        visual_mirror_u = True
                    else:
                        visual_mirror_v = True
            else:
                # fallback a heurística por extremos si la matriz es casi singular
                left_v = min(proj_verts, key=lambda p: p['lx'])
                right_v = max(proj_verts, key=lambda p: p['lx'])
                bottom_v = min(proj_verts, key=lambda p: p['ly'])
                top_v = max(proj_verts, key=lambda p: p['ly'])

                visual_mirror_u = (left_v['uv'].x > right_v['uv'].x + 1e-6)
                visual_mirror_v = (bottom_v['uv'].y > top_v['uv'].y + 1e-6)

        # ------------------------------------------------------------
        # 5. MAPEO A JSON (Intercambio de Ejes)
        # ------------------------------------------------------------
        json_mirror_x = False
        json_mirror_y = False
        
        if angle == 90 or angle == 270:
            # Cruzado
            json_mirror_x = visual_mirror_v
            json_mirror_y = visual_mirror_u
        else:
            # Directo
            json_mirror_x = visual_mirror_u
            json_mirror_y = visual_mirror_v

        # 6. CÁLCULO DEL OFFSET (Matemática Inversa Exacta)
        u_controlled_by_mirror = json_mirror_y if (angle == 90 or angle == 270) else json_mirror_x
        v_controlled_by_mirror = json_mirror_x if (angle == 90 or angle == 270) else json_mirror_y

        # Empezamos en la esquina superior izquierda visual
        json_offset_x = x_left
        json_offset_y = y_top
        
        # Dimensiones para sumar
        dim_u = width_px 
        dim_v = height_px 
        
        # REGLAS DE ROTACIÓN (Sumamos al offset para compensar la resta del importador)
        if angle == 90:
            json_offset_x += dim_u 
        elif angle == 180:
            json_offset_x += dim_u
            json_offset_y += dim_v
        elif angle == 270:
            json_offset_y += dim_v
            
        # REGLAS DE ESPEJO (Si hay mirror, el pivote se mueve al final)
        if visual_mirror_u:
            json_offset_x += dim_u
        if visual_mirror_v:
            json_offset_y += dim_v

        uv_layout[face_name] = {
            "offset": {"x": int(json_offset_x), "y": int(json_offset_y)},
            "mirror": {"x": json_mirror_x, "y": json_mirror_y} if (json_mirror_x or json_mirror_y) else False,
            "angle": int(angle)
        }
        
    return uv_layout


def process_node(obj, out_w, out_h, snap_uvs, id_counter):
    # --- PROCESO TRAS APLICAR INVERSO ---
    loc, rot, sca = obj.matrix_local.decompose()
    
    local_center = mathutils.Vector((0,0,0))
    final_dims = mathutils.Vector((0,0,0))
    has_geometry = False
    
    # NUEVO: Detección de Stretch
    # Usamos la escala del objeto como stretch.
    # Redondeamos a 4 decimales para evitar 1.0000001
    stretch_x = round(sca.x, 4)
    stretch_y = round(sca.z, 4) # Blender Z es Hytale Y
    stretch_z = round(sca.y, 4) # Blender Y es Hytale Z
    
    has_stretch = (stretch_x != 1.0 or stretch_y != 1.0 or stretch_z != 1.0)
    
    if obj.type == 'MESH' and len(obj.data.vertices) > 0:
        # [CAMBIO CRÍTICO]: Obtenemos dimensiones BASADAS EN VÉRTICES (Sin escala de objeto)
        verts = [v.co for v in obj.data.vertices]
        min_v = mathutils.Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
        max_v = mathutils.Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
        
        # Dimensiones puras de la malla (Raw mesh data)
        # NO multiplicamos por obj.scale aquí.
        
        local_center = (min_v + max_v) / 2.0
        final_dims = mathutils.Vector((abs(max_v.x - min_v.x), abs(max_v.y - min_v.y), abs(max_v.z - min_v.z)))
        has_geometry = True

    # --- Normalize name: strip Blender auto-suffixes like ".001", ".002" ---
    base_name = re.sub(r'\.\d+$', '', obj.name)
    final_name = base_name
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
        # Escala Global fija (16.0) para convertir metros a unidades bloque
        scaled = val * FIXED_GLOBAL_SCALE
        if do_snap:
            return int(round(scaled))
        return round(scaled, 4)

    if has_geometry:
        is_plane = (final_dims.x < 0.001) or (final_dims.y < 0.001) or (final_dims.z < 0.001)
        
        # El offset de la forma (shape offset) debe tener en cuenta que 
        # local_center está en espacio sin escalar.
        # Si aplicamos stretch en Hytale, el offset interno también se estira.
        # Por lo general, Hytale aplica el stretch desde el centro del pivote.
        shape_offset = blender_to_hytale_pos(local_center)
        
        # Extraemos UVs (La función nueva)
        texture_layout = extract_uvs(obj, out_w, out_h, snap_to_pixels=snap_uvs)

        hytale_normal = None
        
        # Lógica Box vs Quad
        if is_plane:
            # (Tu lógica de Quads existente, ajustada a get_hytale_size sin obj.scale)
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
            
            # Validación de cara para Quads
            valid_face = None
            for k, v in texture_layout.items():
                if v["offset"]["x"] != 0 or v["offset"]["y"] != 0 or v["angle"] != 0:
                    valid_face = v
                    break
            if not valid_face and texture_layout:
                valid_face = list(texture_layout.values())[0]
            texture_layout = {"front": valid_face} if valid_face else {}
            
        else:
            # Cuboides
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
        
        if hytale_normal: 
            node_data["shape"]["settings"]["normal"] = hytale_normal
        
        # [NUEVO] Inserción de propiedad 'stretch'
        if has_stretch:
            node_data["shape"]["stretch"] = {
                "x": stretch_x,
                "y": stretch_y,
                "z": stretch_z
            }

    for child in obj.children:
        node_data["children"].append(process_node(child, out_w, out_h, snap_uvs, id_counter))

    if not node_data["children"]:
        del node_data["children"]
    
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
    
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    
    if not bm.faces:
        bm.free()
        return

    # Recolectar normales y áreas
    face_data = []
    for f in bm.faces:
        face_data.append((f.normal.copy(), f.calc_area()))
    
    # Ordenar por área (la cara más grande domina)
    face_data.sort(key=lambda x: x[1], reverse=True)
    
    axes = [mathutils.Vector((1,0,0)), mathutils.Vector((-1,0,0)),
            mathutils.Vector((0,1,0)), mathutils.Vector((0,-1,0)),
            mathutils.Vector((0,0,1)), mathutils.Vector((0,0,-1))]

    # 1. Encontrar el Eje Principal (Normal de la cara más grande)
    n1 = face_data[0][0]
    best_axis_1 = max(axes, key=lambda a: n1.dot(a))
    rot1 = n1.rotation_difference(best_axis_1)
    
    # 2. Encontrar el Eje Secundario
    n2 = None
    
    # Intento A: Buscar otra cara perpendicular (Funciona para Cubos)
    for item in face_data:
        n_curr = item[0]
        if abs(n_curr.cross(n1).length) > 0.1: 
            n2 = n_curr
            break
            
    # Intento B: (FIX para Quads) Si no hay cara perpendicular, usar un borde de la cara principal
    if not n2:
        # Buscamos la cara principal en el bmesh (la de mayor área)
        best_face = max(bm.faces, key=lambda f: f.calc_area())
        if best_face and len(best_face.verts) >= 2:
            # Usamos el vector de la primera arista como dirección secundaria
            v1 = best_face.verts[0].co
            v2 = best_face.verts[1].co
            edge_vec = (v2 - v1).normalized()
            
            # Asegurar que no sea paralelo a n1 (matemáticamente imposible en un plano válido, pero por seguridad)
            if abs(edge_vec.cross(n1).length) > 0.01:
                n2 = edge_vec

    rot2 = mathutils.Quaternion() 
    if n2:
        n2_prime = n2.copy()
        n2_prime.rotate(rot1) # Aplicar la primera rotación al vector secundario
        
        # Buscar el eje global más cercano que sea perpendicular a best_axis_1
        valid_axes_2 = [a for a in axes if abs(a.dot(best_axis_1)) < 0.01]
        
        if valid_axes_2:
            best_axis_2 = max(valid_axes_2, key=lambda a: n2_prime.dot(a))
            rot2 = n2_prime.rotation_difference(best_axis_2)
        
    rot_total = rot2 @ rot1
    
    if abs(rot_total.angle) < 0.001:
        bm.free()
        return

    # Aplicar la rotación inversa a la geometría (enderezar malla)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=mathutils.Vector((0,0,0)), matrix=rot_total.to_matrix())
    
    # Aplicar la rotación al objeto (compensar visualmente)
    rotation_to_apply = rot_total.inverted()
    
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = obj.rotation_quaternion @ rotation_to_apply
    
    bm.to_mesh(mesh)
    bm.free()
    obj.data.update()

def process_and_decompose_collection(source_col, temp_col):
    processed_roots = []
    old_to_new = {}
    
    # 1. Copiar objetos a la colección temporal
    for obj in source_col.objects:
        new_obj = obj.copy()
        new_obj.data = obj.data.copy() if obj.data else None
        temp_col.objects.link(new_obj)
        old_to_new[obj] = new_obj
        
    # 2. Restaurar parentesco
    for old_obj, new_obj in old_to_new.items():
        if old_obj.parent and old_obj.parent in old_to_new:
            new_obj.parent = old_to_new[old_obj.parent]
        else:
            processed_roots.append(new_obj)

    # 3. Wrapper inteligente para hermanos (Fix Jerarquías múltiples)
    parent_map = {}
    for obj in temp_col.objects:
        if obj.parent and obj.type == 'MESH':
            if obj.parent not in parent_map:
                parent_map[obj.parent] = []
            parent_map[obj.parent].append(obj)
            
    for parent, children in parent_map.items():
        if len(children) > 1:
            for child in children:
                # Crear Wrapper (Empty)
                clean_child_name = re.sub(r'\.\d+$', '', child.name)
                wrapper_name = f"GRP_{clean_child_name}"
                wrapper = bpy.data.objects.new(wrapper_name, None)
                temp_col.objects.link(wrapper)
                
                # Configurar Wrapper como hijo del padre original con Transform Identidad
                wrapper.parent = parent
                wrapper.matrix_local = mathutils.Matrix.Identity(4)
                
                # Mover el hijo al Wrapper manteniendo su transformación visual
                saved_matrix_local = child.matrix_local.copy()
                child.parent = wrapper
                child.matrix_local = saved_matrix_local

    # --- CAMBIO V0.37: MATRIZ MATEMÁTICA (APPLY PARENT INVERSE) ---
    # En lugar de usar bpy.ops (que falla si no hay contexto visual),
    # calculamos directamente la matriz resultante.
    # Fórmula equivalente a Ctrl+A > Parent Inverse:
    # 1. Nueva Local = MatrizParentInverse * Vieja Local
    # 2. Reset MatrizParentInverse a Identidad
    
    for obj in temp_col.objects:
        if obj.parent:
            # "Quemamos" la relación visual en la transformación local
            obj.matrix_local = obj.matrix_parent_inverse @ obj.matrix_local
            # Reseteamos la inversa (limpieza)
            obj.matrix_parent_inverse.identity()
    # --------------------------------------------------------------

    # 4. Procesar geometrías (Separa loose parts y arregla rotaciones)
    final_objects_to_check = [o for o in temp_col.objects if o.type == 'MESH'] # Lista segura
    
    bpy.ops.object.select_all(action='DESELECT')
    
    for obj in final_objects_to_check:
        if obj.type == 'MESH':
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            if len(obj.data.vertices) > 0:
                bpy.ops.mesh.separate(type='LOOSE')
            
            separated_parts = bpy.context.selected_objects
            
            # Si se separó en partes, actualizar la lista de raíces si es necesario
            if len(separated_parts) > 1 and obj in processed_roots:
                processed_roots.remove(obj)
                for part in separated_parts:
                    if part.parent is None: 
                        processed_roots.append(part)
            
            for part in separated_parts:
                reconstruct_orientation_from_geometry(part)
                part.select_set(False)

    return processed_roots

# ==========================================
#       LÓGICA DE IMPORTACIÓN
# ==========================================

def hytale_to_blender_pos(h_pos):
    # Usamos tu factor de escala 16.0
    x = h_pos.get("x", 0) / 16.0
    y = -h_pos.get("z", 0) / 16.0
    z = h_pos.get("y", 0) / 16.0
    return mathutils.Vector((x, y, z))

def hytale_to_blender_quat(h_quat):
    if not h_quat: return mathutils.Quaternion((1, 0, 0, 0))
    x = h_quat.get("x", 0)
    y = h_quat.get("y", 0)
    z = h_quat.get("z", 0)
    w = h_quat.get("w", 1)
    return mathutils.Quaternion((w, x, -z, y))

def setup_import_material(texture_path, texture_width, texture_height):
    mat_name = "Hytale_Material"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        for n in nodes: nodes.remove(n)
        
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        for input_name in ["Specular", "Specular IOR Level", "Specular Intensity"]:
            if input_name in bsdf.inputs: bsdf.inputs[input_name].default_value = 0.0
        if "Roughness" in bsdf.inputs: bsdf.inputs['Roughness'].default_value = 1.0
            
        output = nodes.new('ShaderNodeOutputMaterial')
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        if texture_path and os.path.exists(texture_path):
            tex_image = nodes.new('ShaderNodeTexImage')
            try:
                img = bpy.data.images.load(texture_path)
                img.alpha_mode = 'STRAIGHT'
                tex_image.image = img
                tex_image.interpolation = 'Closest' 
            except: pass
            if 'Base Color' in bsdf.inputs: links.new(tex_image.outputs['Color'], bsdf.inputs['Base Color'])
            if 'Alpha' in bsdf.inputs: links.new(tex_image.outputs['Alpha'], bsdf.inputs['Alpha'])
                
            mat.blend_method = 'CLIP'
            mat.shadow_method = 'CLIP'
    return mat

def apply_uvs_smart(face, bm, data, tex_w, tex_h, fw, fh):
    if not bm.loops.layers.uv: bm.loops.layers.uv.new()
    uv_layer = bm.loops.layers.uv.active
    
    # --- 1. DATOS CRUDOS ---
    off_x = data.get("offset", {}).get("x", 0)
    off_y = data.get("offset", {}).get("y", 0)
    
    raw_ang = data.get("angle", 0)
    try:
        ang = int(raw_ang) % 360 
    except:
        ang = 0
    
    mirror = data.get("mirror", {})
    mir_x = mirror if isinstance(mirror, bool) else bool(mirror.get("x", False))
    mir_y = False if isinstance(mirror, bool) else bool(mirror.get("y", False))

    # --- 2. DIMENSIONES ABSOLUTAS ---
    is_rotated = (ang == 90 or ang == 270)
    
    # Dimensiones visuales
    size_u = fh if is_rotated else fw
    size_v = fw if is_rotated else fh
    
    # --- 3. DETECTAR QUÉ EJE DE LA TEXTURA SE INVIERTE ---
    # Al rotar 90°, el eje X del JSON (Mirror X) afecta visualmente a la altura (V).
    if ang == 0 or ang == 180:
        u_is_mirrored = mir_x
        v_is_mirrored = mir_y
    else: # 90 o 270
        u_is_mirrored = mir_y
        v_is_mirrored = mir_x

    # --- 4. CÁLCULO DEL OFFSET (POSICIÓN) ---
    base_x = off_x
    base_y = off_y
    
    # Ajuste de punto de anclaje por rotación
    if ang == 90:
        base_x = off_x - size_u
    elif ang == 180:
        base_x = off_x - size_u
        base_y = off_y - size_v
    elif ang == 270:
        base_y = off_y - size_v

    # Corrección de posición por Espejo:
    # Si Hytale invierte un eje, el offset define el punto final, no el inicial.
    # Desplazamos la caja hacia atrás en el eje afectado.
    if u_is_mirrored:
        base_x -= size_u
    if v_is_mirrored:
        base_y -= size_v

    # --- 5. CÁLCULO DE COORDENADAS ---
    x_min = base_x
    x_max = base_x + size_u
    y_min = base_y
    y_max = base_y + size_v
    
    # Aplicamos el espejo GEOMÉTRICAMENTE intercambiando límites.
    # Esto ya deja la textura "al revés" en el eje correcto antes de rotar.
    if u_is_mirrored:
        u_left, u_right = x_max / tex_w, x_min / tex_w
    else:
        u_left, u_right = x_min / tex_w, x_max / tex_w
        
    if v_is_mirrored:
        v_top = y_max / tex_h
        v_bottom = y_min / tex_h
    else:
        v_top = y_min / tex_h
        v_bottom = y_max / tex_h
        
    # Convertir a espacio Blender (1.0 - V)
    vt = 1.0 - v_top
    vb = 1.0 - v_bottom
    
    # Lista Base (TL, TR, BR, BL)
    coords = [(u_left, vt), (u_right, vt), (u_right, vb), (u_left, vb)]

    # --- 6. APLICAR ROTACIÓN (WINDING ORDER) ---
    step = 0
    if ang == 90: step = 1
    elif ang == 180: step = 2
    elif ang == 270: step = 3

    # [CORRECCIÓN FINAL]: Eliminamos el "step += 2".
    # Al haber calculado bien el "u_is_mirrored" y el "offset" arriba,
    # la rotación estándar ya coloca cada vértice en su lugar.
    # El "+2" anterior era lo que estaba causando el error de 180 grados.

    step = step % 4
    coords = coords[step:] + coords[:step]

    # --- 7. MAPEO GEOMÉTRICO (ESTÁNDAR) ---
    from mathutils import Vector
    bmesh.ops.split_edges(bm, edges=face.edges)

    normal = face.normal
    center = face.calc_center_median()
    epsilon = 0.9
    
    if normal.z > epsilon:    # TOP
        ref_up = Vector((0, 1, 0)); ref_right = Vector((1, 0, 0))   
    elif normal.z < -epsilon: # BOTTOM
        ref_up = Vector((0, -1, 0)); ref_right = Vector((1, 0, 0))
    elif normal.y > epsilon:  # BACK
        ref_up = Vector((0, 0, 1)); ref_right = Vector((-1, 0, 0))
    elif normal.y < -epsilon: # FRONT
        ref_up = Vector((0, 0, 1)); ref_right = Vector((1, 0, 0))
    elif normal.x > epsilon:  # RIGHT
        ref_up = Vector((0, 0, 1)); ref_right = Vector((0, 1, 0))
    elif normal.x < -epsilon: # LEFT
        ref_up = Vector((0, 0, 1)); ref_right = Vector((0, -1, 0))
    else: 
        ref_up = Vector((0, 0, 1)); ref_right = ref_up.cross(normal)

    for loop in face.loops:
        vert_vec = loop.vert.co - center
        dx = vert_vec.dot(ref_right)
        dy = vert_vec.dot(ref_up)
        
        idx = 0
        if dx < 0 and dy > 0:   idx = 0 
        elif dx > 0 and dy > 0: idx = 1 
        elif dx > 0 and dy < 0: idx = 2 
        elif dx < 0 and dy < 0: idx = 3 
        else: 
            if dx <= 0 and dy >= 0: idx = 0
            elif dx >= 0 and dy >= 0: idx = 1
            elif dx >= 0 and dy <= 0: idx = 2
            elif dx <= 0 and dy <= 0: idx = 3
            
        loop[uv_layer].uv = coords[idx]

# ### NUEVO: Se añade el argumento 'stretch' para deformar la malla
def create_mesh_box_import(name, shape_data, texture_width, texture_height):
    settings = shape_data.get("settings", {})
    size = settings.get("size", {})
    hx, hy, hz = size.get("x", 0), size.get("y", 0), size.get("z", 0)
    
    # 1. Dimensiones Base
    dx, dy, dz = (hx / 16.0)/2.0, (hz / 16.0)/2.0, (hy / 16.0)/2.0
    
    bm = bmesh.new()
    # Vértices (X, -Z, Y en Blender para mapear Hytale)
    # 0: BL-Front, 1: BR-Front, 2: BR-Back, 3: BL-Back (Inferiores)
    # 4: TL-Front, 5: TR-Front, 6: TR-Back, 7: TL-Back (Superiores)
    v = [bm.verts.new((-dx, -dy, -dz)), bm.verts.new((dx, -dy, -dz)),
         bm.verts.new((dx, dy, -dz)), bm.verts.new((-dx, dy, -dz)),
         bm.verts.new((-dx, -dy, dz)), bm.verts.new((dx, -dy, dz)),
         bm.verts.new((dx, dy, dz)), bm.verts.new((-dx, dy, dz))]
    
    # --- CORRECCIÓN DE WINDING (Normales Manuales) ---
    # Definimos los vértices en sentido anti-horario (CCW) mirando desde fuera.
    # Esto garantiza que las normales sean correctas sin usar recalc_normals.
    face_map = {
        "top":    (v[4], v[5], v[6], v[7]), # Correcto (+Z)
        "bottom": (v[0], v[3], v[2], v[1]), # CORREGIDO: (Antes era 0,1,2,3 -> Invertido). Ahora (-Z)
        "front":  (v[0], v[1], v[5], v[4]), # Correcto (-Y)
        "back":   (v[2], v[3], v[7], v[6]), # Correcto (+Y)
        "left":   (v[3], v[0], v[4], v[7]), # Correcto (-X)
        "right":  (v[1], v[2], v[6], v[5])  # Correcto (+X)
    }

    tex_layout = shape_data.get("textureLayout", {})
    for f_name, f_verts in face_map.items():
        if f_name in tex_layout:
            try:
                # Al crear la cara con el orden correcto, los índices de loops [0,1,2,3]
                # son estables y predecibles para la función apply_uvs_smart.
                f = bm.faces.new(f_verts)
                
                # Asignar dimensiones UV
                if f_name in ['top', 'bottom']: fw, fh = hx, hz
                elif f_name in ['front', 'back']: fw, fh = hx, hy
                else: fw, fh = hz, hy
                
                apply_uvs_smart(f, bm, tex_layout[f_name], texture_width, texture_height, fw, fh)
            except ValueError:
                pass # Evita error si la cara ya existe (raro en cubos)
            except Exception:
                pass

    # --- IMPORTANTE: ELIMINADO recalc_face_normals ---
    # Al quitar esto, evitamos que Blender decida invertir caras arbitrariamente,
    # lo cual causaba que las UVs se rotaran 180 grados o se desapilaran.
    # bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bm.to_mesh(mesh)
    bm.free()
    
    # Aplicar offset
    obj_off = hytale_to_blender_pos(shape_data.get("offset", {}))
    for vert in mesh.vertices: vert.co += obj_off
    return mesh
    
def create_mesh_quad_import(name, shape_data, texture_width, texture_height):
    settings = shape_data.get("settings", {})
    size = settings.get("size", {})
    n = settings.get("normal", "+Y")
    
    # Tamaño base 1:1 con el archivo
    dx = (size.get('x', 16) / 16.0) / 2.0
    dy = (size.get('y', 16) / 16.0) / 2.0
    
    bm = bmesh.new()
    v_pos = []
    if n == "+Y": v_pos = [(-dx, -dy, 0), (dx, -dy, 0), (dx, dy, 0), (-dx, dy, 0)]
    elif n == "-Y": v_pos = [(-dx, dy, 0), (dx, dy, 0), (dx, -dy, 0), (-dx, -dy, 0)]
    elif n == "+Z": v_pos = [(-dx, 0, -dy), (dx, 0, -dy), (dx, 0, dy), (-dx, 0, dy)]
    elif n == "-Z": v_pos = [(dx, 0, -dy), (-dx, 0, -dy), (-dx, 0, dy), (dx, 0, dy)]
    elif n == "+X": v_pos = [(0, -dx, -dy), (0, dx, -dy), (0, dx, dy), (0, -dx, dy)]
    else: v_pos = [(0, dx, -dy), (0, -dx, -dy), (0, -dx, dy), (0, dx, dy)]
            
    try:
        v_objs = [bm.verts.new(p) for p in v_pos]
        f = bm.faces.new(v_objs)
        tex_layout = shape_data.get("textureLayout", {})
        f_name = list(tex_layout.keys())[0] if tex_layout else "front"
        apply_uvs_smart(f, bm, tex_layout.get(f_name, {}), texture_width, texture_height, size['x'], size['y'])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    except: pass

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    off_h = hytale_to_blender_pos(shape_data.get("offset", {}))
    for v in mesh.vertices: v.co += off_h
    return mesh

def process_node_import(node_data, parent_obj, texture_width, texture_height, collection):
    name = node_data.get("name", "Node")
    pos = hytale_to_blender_pos(node_data.get("position", {}))
    rot = hytale_to_blender_quat(node_data.get("orientation", {}))
    
    # --- 1. CREAR EL NODO PRINCIPAL (PIVOTE) ---
    node_empty = bpy.data.objects.new(name, None)
    node_empty.empty_display_type = 'PLAIN_AXES'
    node_empty.empty_display_size = 0.2
    collection.objects.link(node_empty)
    
    node_empty.location = pos
    node_empty.rotation_mode = 'QUATERNION'
    node_empty.rotation_quaternion = rot
    
    # Emparentar el Empty al padre (si existe)
    if parent_obj:
        node_empty.parent = parent_obj
    
    # --- PRE-VERIFICACIÓN DE HIJOS ---
    children_list = node_data.get("children", [])
    has_children = len(children_list) > 0

    # --- 2. CREAR LA FORMA (MESH) ---
    shape_data = node_data.get("shape", {})
    shape_type = shape_data.get("type", "none")
    
    if shape_type != "none":
        st = shape_data.get("stretch", {'x': 1.0, 'y': 1.0, 'z': 1.0})
        mesh_obj = None # Inicializamos la variable

        if has_children:
            # Lógica para jerarquía avanzada (Padre -> Wrapper -> Malla)
            shape_copy = shape_data.copy()
            shape_copy['offset'] = {'x': 0, 'y': 0, 'z': 0}

            if shape_type == 'box':
                mesh = create_mesh_box_import(name + "_mesh", shape_copy, texture_width, texture_height)
            else:
                mesh = create_mesh_quad_import(name + "_mesh", shape_copy, texture_width, texture_height)
            
            mesh_obj = bpy.data.objects.new(name + "_shape", mesh)
            collection.objects.link(mesh_obj)

            # Calcular Offset para el Wrapper
            raw_offset = shape_data.get("offset", {'x': 0, 'y': 0, 'z': 0})
            target_pos = hytale_to_blender_pos(raw_offset)
            
            # Crear el Wrapper (Geo)
            geo_wrapper = bpy.data.objects.new(name + "_Geo", None)
            geo_wrapper.empty_display_type = 'PLAIN_AXES'
            geo_wrapper.empty_display_size = 0.1
            collection.objects.link(geo_wrapper)
            
            # EMPARENTAMIENTO EN CADENA
            geo_wrapper.parent = node_empty
            geo_wrapper.location = target_pos
            mesh_obj.parent = geo_wrapper
            
        else:
            # Caso Normal: Malla directa al Empty
            if shape_type == 'box':
                mesh = create_mesh_box_import(name + "_mesh", shape_data, texture_width, texture_height)
            else:
                mesh = create_mesh_quad_import(name + "_mesh", shape_data, texture_width, texture_height)
                
            mesh_obj = bpy.data.objects.new(name + "_shape", mesh)
            collection.objects.link(mesh_obj)
            
            # EMPARENTAMIENTO DIRECTO
            mesh_obj.parent = node_empty
            
        # Aplicar escala (esto ahora se hace después de asegurar que mesh_obj existe)
        if mesh_obj:
            mesh_obj.scale = (st.get('x', 1.0), st.get('z', 1.0), st.get('y', 1.0))

    # --- 3. PROCESAR HIJOS ---
    for child in children_list:
        process_node_import(child, node_empty, texture_width, texture_height, collection)
        
    return node_empty
    
# --- OPERADORES ---

class OPS_OT_SetupHytaleScene(bpy.types.Operator):
    bl_idname = "hytale.setup_scene"
    bl_label = "Configurar Escena"
    def execute(self, context):
        context.scene.unit_settings.system = 'NONE'
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.overlay.show_floor = True
                        space.overlay.grid_scale = 2.0      
                        space.overlay.grid_subdivisions = 16 
        return {'FINISHED'}

class OPS_OT_LoadReference(bpy.types.Operator):
    bl_idname = "hytale.load_reference"
    bl_label = "Cargar Referencia"
    def execute(self, context):
        props = context.scene.hytale_props
        filename = props.selected_reference
        if filename == 'NONE': return {'CANCELLED'}
        folder_path = get_templates_path()
        filepath = os.path.join(folder_path, filename)
        if not os.path.exists(filepath): return {'CANCELLED'}
        try:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                data_to.collections = data_from.collections
            for col in data_to.collections:
                if col is not None: context.scene.collection.children.link(col)
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}

class OPS_OT_ExportHytale(bpy.types.Operator):
    bl_idname = "hytale.export_model"
    bl_label = "Exportar Modelo Hytale"
    
    def invoke(self, context, event):
        props = context.scene.hytale_props
        # CAMBIO: Usamos la colección directa
        target_col = props.target_collection
        issues_found = False
        
        # 1. Validación básica: ¿Existe la colección?
        if not target_col:
            self.report({'ERROR'}, "Por favor, selecciona una colección.")
            return {'CANCELLED'}
        
        # Validación rápida de seguridad
        # Iteramos directamente sobre 'target_col'
        for obj in target_col.objects:
            if obj.type == 'MESH':
                if obj.scale.x < 0 or obj.scale.y < 0 or obj.scale.z < 0: issues_found = True
                if not obj.data.materials: issues_found = True
                if len(obj.data.vertices) > 8: issues_found = True
                if obj.parent and obj.parent.type == 'MESH': issues_found = True
        
        if issues_found:
             return context.window_manager.invoke_props_dialog(self, width=600)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.ui_units_x = 20
        col = layout.column()
        col.alert = True
        col.label(text="¡ADVERTENCIA!", icon='ERROR')
        col.label(text="Errores detectados. ¿Exportar de todas formas?")

    def execute(self, context):
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        props = context.scene.hytale_props
        target_col = props.target_collection
        
        if not target_col:
            self.report({'ERROR'}, "No has seleccionado ninguna colección.")
            return {'CANCELLED'}
            
        output_path = bpy.path.abspath(props.file_path)
        if not output_path:
            self.report({'ERROR'}, "Ruta de archivo no definida.")
            return {'CANCELLED'}
        if not output_path.lower().endswith(".blockymodel"): output_path += ".blockymodel"
        
        # --- LÓGICA DE TEXTURA / RESOLUCIÓN ---
        tex_w, tex_h = 32, 32 # Valor por defecto seguro
        
        if props.resolution_mode == 'IMAGE':
            if props.target_image:
                tex_w = props.target_image.size[0]
                tex_h = props.target_image.size[1]
            else:
                self.report({'WARNING'}, "Modo Textura activado pero sin imagen. Usando 32x32.")
        else:
            # Modo Manual
            tex_w = props.tex_width
            tex_h = props.tex_height
        # --------------------------------------
        
        # Crear colección temporal para procesar sin destruir la escena
        temp_col = bpy.data.collections.new("Hytale_Export_Temp")
        context.scene.collection.children.link(temp_col)
        
        try:
            # Procesamos la colección (separa jerarquía, arregla rotaciones)
            processed_roots = process_and_decompose_collection(target_col, temp_col)
            
            id_counter = [0]
            # Pasamos las dimensiones (tex_w, tex_h) calculadas arriba
            nodes_array = [process_node(root, tex_w, tex_h, props.snap_uvs, id_counter) for root in processed_roots]
            
            final_json = { 
                "nodes": nodes_array, 
                "format": "character", 
                "textureWidth": int(tex_w), 
                "textureHeight": int(tex_h) 
            }
            
            # --- BLOQUE OPTIMIZADO: Formato Compacto (Opción B) ---
            def write_blockymodel_mixed_to_string(data, indent=1,
                                                  inline_keys=('vertices','uvs','data','indices','colors'),
                                                  min_items_to_inline=1):
                """
                Serializa `data` a JSON con indentación reducida (indent),
                y luego compacta arrays de ciertas keys a una sola línea para ahorrar espacio.
                Devuelve el string final.
                """
                # 1) Serializamos con indent simple
                json_str = json.dumps(data, indent=indent, ensure_ascii=False)
                
                # 2) Compactar arrays de keys objetivo (regex sobre el JSON formateado)
                for key in inline_keys:
                    pattern = r'("'+re.escape(key)+r'"\s*:\s*)\[\s*(.*?)\s*\]'
                    def repl(m):
                        prefix = m.group(1)
                        inner = m.group(2)
                        approx_elements = inner.count(',') + 1 if inner.strip() != '' else 0
                        if approx_elements < min_items_to_inline:
                            return m.group(0)
                        compact = re.sub(r'\s+', ' ', inner)
                        compact = re.sub(r'\s*,\s*', ',', compact)
                        compact = re.sub(r'\s*:\s*', ':', compact)
                        return prefix + '[' + compact.strip() + ']'
                    json_str = re.sub(pattern, repl, json_str, flags=re.DOTALL)

                return json_str

            # Generar JSON parcialmente compactado en memoria
            json_str = write_blockymodel_mixed_to_string(final_json, indent=1,
                                                         inline_keys=('vertices','uvs','data','indices','colors'),
                                                         min_items_to_inline=1)

            # 3) Extra: Colapsar vectores/quat en una sola línea (más robusto con floats y exponentes)
            float_pat = r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
            # Vector {x,y,z}
            json_str = re.sub(
                r'\{\s*"x"\s*:\s*' + float_pat + r'\s*,\s*"y"\s*:\s*' + float_pat + r'\s*,\s*"z"\s*:\s*' + float_pat + r'\s*\}',
                r'{"x": \1, "y": \2, "z": \3}',
                json_str,
                flags=re.DOTALL
            )
            # Quaternion {x,y,z,w}
            json_str = re.sub(
                r'\{\s*"x"\s*:\s*' + float_pat + r'\s*,\s*"y"\s*:\s*' + float_pat + r'\s*,\s*"z"\s*:\s*' + float_pat + r'\s*,\s*"w"\s*:\s*' + float_pat + r'\s*\}',
                r'{"x": \1, "y": \2, "z": \3, "w": \4}',
                json_str,
                flags=re.DOTALL
            )

            # 4) (Opcional) Compactar pequeños objetos de 2 componentes {"u", "v"} -> {"u":..., "v":...}
            json_str = re.sub(
                r'\{\s*"u"\s*:\s*' + float_pat + r'\s*,\s*"v"\s*:\s*' + float_pat + r'\s*\}',
                r'{"u": \1, "v": \2}',
                json_str,
                flags=re.DOTALL
            )
            
            # --- Compactar objetos 2-componentes {x, y} (p.ej. offset) ---
            json_str = re.sub(
                r'\{\s*"x"\s*:\s*' + float_pat + r'\s*,\s*"y"\s*:\s*' + float_pat + r'\s*\}',
                r'{"x": \1, "y": \2}',
                json_str,
                flags=re.DOTALL
            )

            # 5) Escritura final
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
                
            self.report({'INFO'}, f"Exportado exitosamente: {output_path}")

        except Exception as e:
            self.report({'ERROR'}, f"Error Crítico: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
            
        finally:
            # Limpieza de temporales
            if temp_col:
                for obj in temp_col.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.collections.remove(temp_col)

        return {'FINISHED'}


# 1. Definimos las opciones de resolución (Múltiplos de 32)
# Esto genera una lista de tuplas: ('32', '32', ''), ('64', '64', ''), etc.
hytale_res_list = [('0', "Automático (JSON)", "Usa los valores del archivo")]
for i in range(1, 33):
    val = str(i * 32)
    hytale_res_list.append((val, val, f"Resolución {val}px"))

class OPS_OT_ImportHytale(bpy.types.Operator, ImportHelper):
    bl_idname = "hytale.import_model"
    bl_label = "Importar Modelo Hytale"
    filename_ext = ".blockymodel"
    
    res_w: bpy.props.EnumProperty(
        name="Ancho UV",
        items=hytale_res_list,
        default='0'
    )
    res_h: bpy.props.EnumProperty(
        name="Alto UV",
        items=hytale_res_list,
        default='0'
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Resolución UV Manual", icon='UV_DATA')
        row = box.row(align=True)
        row.prop(self, "res_w", text="W")
        row.prop(self, "res_h", text="H")

    def execute(self, context):
        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}

        # Lógica de resolución: Prioridad al menú, luego al JSON
        tex_w = int(self.res_w) if self.res_w != '0' else data.get("textureWidth", 32)
        tex_h = int(self.res_h) if self.res_h != '0' else data.get("textureHeight", 32)

        model_name = os.path.splitext(os.path.basename(self.filepath))[0]
        col = bpy.data.collections.new(model_name)
        context.scene.collection.children.link(col)

        # Iniciar importación recursiva
        for node in data.get("nodes", []):
            process_node_import(node, None, tex_w, tex_h, col)

        self.report({'INFO'}, f"Importado con resolución: {tex_w}x{tex_h}")
        return {'FINISHED'}

class OPS_OT_PixelPerfectPack(bpy.types.Operator):
    bl_idname = "hytale.pixel_perfect_pack"
    bl_label = "Scale UV's To Pixel Perfect"
    bl_description = "Alinea, escala y (opcionalmente) stackea UVs por intersección."

    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'WARNING'}, "Selecciona al menos un objeto Mesh")
            return {'CANCELLED'}

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        context.view_layer.objects.active = selected_meshes[0]
        bpy.ops.object.join()
        main_obj = context.active_object
        
        # 1. Reconstrucción de orientación para cálculos precisos (también usa el FIX)
        reconstruct_orientation_from_geometry(main_obj)
        
        props = context.scene.hytale_props
        tex_w, tex_h = get_image_size_from_objects([main_obj])
        if not tex_w: tex_w, tex_h = 32, 32

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(main_obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        
        # --- PASO 1: UNWRAP ---
        bpy.ops.mesh.select_all(action='SELECT')
        if props.new_unwrap:
            try:
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001, correct_aspect=True)
            except:
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)

        # --- PASO 2: ALINEACIÓN (API Moderna) ---
        area_uv = next((a for a in context.screen.areas if a.type == 'IMAGE_EDITOR'), None)
        if area_uv:
            with context.temp_override(area=area_uv):
                try: 
                    bpy.ops.uv.select_all(action='SELECT')
                    bpy.ops.uv.align_rotation(method='AUTO', correct_aspect=True)
                except: pass
        
        bmesh.update_edit_mesh(main_obj.data)

        # --- PASO 3: ESCALADO PIXEL PERFECT ---
        all_loops = [l for f in bm.faces for l in f.loops]
        if not all_loops:
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}

        min_u_global = min(l[uv_layer].uv.x for l in all_loops)
        max_u_global = max(l[uv_layer].uv.x for l in all_loops)
        min_v_global = min(l[uv_layer].uv.y for l in all_loops)
        max_v_global = max(l[uv_layer].uv.y for l in all_loops)

        dominant_face = max(bm.faces, key=lambda f: f.calc_area())
        v0, v1, v3 = dominant_face.loops[0].vert.co, dominant_face.loops[1].vert.co, dominant_face.loops[-1].vert.co
        w_3d = mathutils.Vector(((v1.x-v0.x)*main_obj.scale.x, (v1.y-v0.y)*main_obj.scale.y, (v1.z-v0.z)*main_obj.scale.z)).length
        h_3d = mathutils.Vector(((v3.x-v0.x)*main_obj.scale.x, (v3.y-v0.y)*main_obj.scale.y, (v3.z-v0.z)*main_obj.scale.z)).length

        uvs_dom = [l[uv_layer].uv for l in dominant_face.loops]
        curr_w_uv = max(0.0001, max(u.x for u in uvs_dom) - min(u.x for u in uvs_dom))
        curr_h_uv = max(0.0001, max(u.y for u in uvs_dom) - min(u.y for u in uvs_dom))

        scale_u = (w_3d * 16.0 / tex_w) / curr_w_uv
        scale_v = (h_3d * 16.0 / tex_h) / curr_h_uv

        pivot = mathutils.Vector(((min_u_global + max_u_global) / 2.0, (min_v_global + max_v_global) / 2.0))
        for f in bm.faces:
            for l in f.loops:
                l[uv_layer].uv.x = pivot.x + (l[uv_layer].uv.x - pivot.x) * scale_u
                l[uv_layer].uv.y = pivot.y + (l[uv_layer].uv.y - pivot.y) * scale_v
                if props.snap_uvs:
                    l[uv_layer].uv.x = round(l[uv_layer].uv.x * tex_w) / tex_w
                    l[uv_layer].uv.y = round(l[uv_layer].uv.y * tex_h) / tex_h

        bmesh.update_edit_mesh(main_obj.data)

        # --- PASO 4: AUTO-STACK POR INTERSECCIÓN (OPCIONAL) ---
        if props.auto_stack:
            # Funciones internas para detectar islas y dimensiones
            def get_islands(bm, uv_layer):
                all_faces = set(bm.faces)
                islands = []
                while all_faces:
                    face = all_faces.pop()
                    island = {face}
                    stack = [face]
                    while stack:
                        f = stack.pop()
                        for edge in f.edges:
                            for neighbor in edge.link_faces:
                                if neighbor in all_faces:
                                    is_joined = False
                                    for l1 in f.loops:
                                        if l1.edge == edge:
                                            for l2 in neighbor.loops:
                                                if l2.edge == edge:
                                                    if (l1[uv_layer].uv - l2[uv_layer].uv).length < 0.0001:
                                                        is_joined = True; break
                                    if is_joined:
                                        island.add(neighbor); stack.append(neighbor); all_faces.remove(neighbor)
                    islands.append(island)
                return islands

            def get_island_stats(island, uv_layer):
                uvs = [l[uv_layer].uv for f in island for l in f.loops]
                mi_u = min(u.x for u in uvs); ma_u = max(u.x for u in uvs)
                mi_v = min(u.y for u in uvs); ma_v = max(u.y for u in uvs)
                return {
                    'min_u': mi_u, 'max_u': ma_u, 'min_v': mi_v, 'max_v': ma_v,
                    'w': round(ma_u - mi_u, 5), 'h': round(ma_v - mi_v, 5),
                    'min_corner': mathutils.Vector((mi_u, mi_v))
                }

            bm.faces.ensure_lookup_table()
            islands = get_islands(bm, uv_layer)
            stats = [get_island_stats(isl, uv_layer) for isl in islands]
            
            for i in range(len(stats)):
                for j in range(i + 1, len(stats)):
                    A = stats[i]
                    B = stats[j]
                    
                    # Detección de colisión AABB
                    overlap = not (A['max_u'] < B['min_u'] or A['min_u'] > B['max_u'] or 
                                   A['max_v'] < B['min_v'] or A['min_v'] > B['max_v'])
                    
                    if overlap:
                        if abs(A['w'] - B['w']) < 0.001 and abs(A['h'] - B['h']) < 0.001:
                            diff = A['min_corner'] - B['min_corner']
                            for f in islands[j]:
                                for l in f.loops:
                                    l[uv_layer].uv += diff
                            
                            B['min_corner'] += diff
                            B['min_u'] += diff.x; B['max_u'] += diff.x
                            B['min_v'] += diff.y; B['max_v'] += diff.y

        # --- AJUSTE AL LIENZO ---
        bmesh.update_edit_mesh(main_obj.data); curu, curv = [l[uv_layer].uv.x for f in bm.faces for l in f.loops], [l[uv_layer].uv.y for f in bm.faces for l in f.loops]
        offu, offv = -min(curu) if min(curu) < 0 else (1.0 - max(curu) if max(curu) > 1.0 else 0), -min(curv) if min(curv) < 0 else (1.0 - max(curv) if max(curv) > 1.0 else 0)
        if offu != 0.0 or offv != 0.0:
            for face in bm.faces:
                for loop in face.loops: loop[uv_layer].uv.x += offu; loop[uv_layer].uv.y += offv
        bmesh.update_edit_mesh(main_obj.data); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, "Cube2D: Proceso Pixel Perfect finalizado."); return {'FINISHED'}

def update_material_texture(self, context):
    """Busca la textura conectada al Base Color del material seleccionado"""
    mat = self.target_material
    if not mat or not mat.use_nodes:
        return
    
    # Buscar el nodo Principled BSDF
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf and bsdf.inputs['Base Color'].is_linked:
        # Obtener el nodo conectado al color base
        link = bsdf.inputs['Base Color'].links[0]
        node = link.from_node
        if node.type == 'TEX_IMAGE' and node.image:
            self.target_image = node.image 

def update_target_texture(self, context):
    """
    Callback: Aplica la imagen seleccionada al nodo de textura del 'target_material'.
    Ya no iteramos objetos, modificamos directamente el material compartido.
    """
    target_img = self.target_image
    mat = self.target_material # Usamos el material global seleccionado
    
    if not target_img or not mat: return
    
    # --- Configuración de Nodos del Material ---
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    # 1. Buscar o Crear Principled BSDF
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf:
        nodes.clear() # Limpiamos si estaba sucio
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        out = nodes.new('ShaderNodeOutputMaterial')
        out.location = (300, 0)
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    
    # 2. Buscar o Crear Nodo de Imagen
    tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
    if not tex_node:
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.location = (-300, 200)
    
    # 3. Asignar Imagen y Configurar
    tex_node.image = target_img
    tex_node.interpolation = 'Closest' # Pixel Art style
    
    # 4. Conectar
    if 'Base Color' in bsdf.inputs:
        links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
    if 'Alpha' in bsdf.inputs:
        links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
        
    # 5. Configurar Transparencia
    mat.blend_method = 'CLIP'
    mat.shadow_method = 'CLIP'

# --- UI Y PANEL ---

class HytaleProperties(bpy.types.PropertyGroup):
    target_collection: bpy.props.PointerProperty(
        name="Colección",
        type=bpy.types.Collection,
        description="Selecciona la colección del modelo para habilitar las demás herramientas"
    )
    
    # Al seleccionar el material, dispara la función 'update_material_texture'
    target_material: bpy.props.PointerProperty(
        name="Material Unificado",
        type=bpy.types.Material,
        description="Material principal del modelo",
        update=update_material_texture 
    )
    
    # --- SISTEMA DE SELECCIÓN DE TEXTURA ---
    resolution_mode: bpy.props.EnumProperty(
        name="Modo de Resolución",
        description="Elige de dónde obtener el tamaño del mapa UV",
        items=[
            ('IMAGE', "Usar Textura (Skin)", "El tamaño se tomará de la imagen seleccionada", 'IMAGE_DATA', 0),
            ('CUSTOM', "Manual (Sin Textura)", "Escribir el tamaño manualmente", 'EDITMODE_HLT', 1)
        ],
        default='IMAGE'
    )
    
    target_image: bpy.props.PointerProperty(
        name="Textura del Modelo",
        type=bpy.types.Image,
        description="Selecciona la imagen/textura que usará este modelo",
        update=update_target_texture
    )
    # ---------------------------------------

    tex_width: bpy.props.IntProperty(
        name="Ancho (W)",
        default=32,
        min=1
    )
    tex_height: bpy.props.IntProperty(
        name="Alto (H)",
        default=32,
        min=1
    )
    
    snap_uvs: bpy.props.BoolProperty(
        name="Snap UVs a Píxeles",
        default=True
    )
    file_path: bpy.props.StringProperty(name="Guardar como", default="//modelo.blockymodel", subtype='FILE_PATH')
    
    # Props de configuración de escena y UVs
    setup_pixel_grid: bpy.props.BoolProperty(name="Setup Pixel Perfect", default=False, update=update_hytale_grid_setup)
    show_subdivisions: bpy.props.BoolProperty(name="Ver Subdivisiones", default=False, update=update_grid_subdivisions)
    new_unwrap: bpy.props.BoolProperty(name="Generar Nuevo Unwrap", default=False)
    auto_stack: bpy.props.BoolProperty(name="Auto Stack Similar", default=False) 
    selected_reference: bpy.props.EnumProperty(name="Referencia", items=get_templates_list)
    
# --- VARIABLES GLOBALES ---
uv_measures_running = False
# Estas variables guardarán SIEMPRE la posición del último clic válido
last_click_abs_x = 0  
last_click_abs_y = 0
draw_handle_uv_stats = None

def draw_uv_stats_callback(self, context):
    global last_click_abs_x, last_click_abs_y
    
    # 1. Validar contexto
    objects_in_edit = [o for o in context.selected_objects if o.type == 'MESH' and o.mode == 'EDIT']
    if not objects_in_edit: return

    region = context.region 
    scene = context.scene
    
    # --- LA LÓGICA DE ORO ---
    # Calculamos la posición del objetivo basándonos en el ÚLTIMO CLIC guardado.
    # Restamos region.x/y para convertir la coordenada absoluta de la ventana
    # a la coordenada local de este editor UV específico.
    target_x = last_click_abs_x - region.x
    target_y = last_click_abs_y - region.y

    # Configuración de Fuente
    font_id = 0
    try: blf.size(font_id, 15)
    except: pass
    blf.color(font_id, 1, 0.9, 0, 1) 
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0, 0, 0, 0.8)

    # Configuración Global
    use_sync = scene.tool_settings.use_uv_select_sync
    
    # Detección de Modo
    show_edges = False
    show_faces = False
    if use_sync:
        msm = context.tool_settings.mesh_select_mode
        if msm[0] or msm[1]: show_edges = True
        if msm[2]: show_faces = True
    else:
        usm = context.tool_settings.uv_select_mode
        if usm in {'VERTEX', 'EDGE'}: show_edges = True
        if usm in {'FACE', 'ISLAND'}: show_faces = True

    def uv_to_region(u, v):
        x, y = region.view2d.view_to_region(u, v)
        return int(x), int(y)

    candidates = {}

    for obj in objects_in_edit:
        bm = None
        try:
            me = obj.data
            bm_orig = bmesh.from_edit_mesh(me)
            bm = bm_orig.copy()
            
            uv_layer = bm.loops.layers.uv.active
            if not uv_layer:
                bm.free()
                continue

            tex_w, tex_h = 32, 32
            if obj.active_material and obj.active_material.use_nodes:
                try:
                    for n in obj.active_material.node_tree.nodes:
                        if n.type == 'TEX_IMAGE' and n.image:
                            tex_w, tex_h = n.image.size
                            break
                except: pass

            # --- RECOLECTAR BORDES ---
            if show_edges:
                for face in bm.faces:
                    for loop in face.loops:
                        l_curr = loop
                        l_next = loop.link_loop_next
                        
                        u_data1 = l_curr[uv_layer]
                        u_data2 = l_next[uv_layer]
                        
                        is_selected = False
                        if use_sync:
                            if l_curr.edge.select: is_selected = True
                        else:
                            if u_data1.select and u_data2.select: is_selected = True
                        
                        if not is_selected: continue
                        
                        uv1 = u_data1.uv
                        uv2 = u_data2.uv
                        
                        mid_u = (uv1.x + uv2.x) / 2
                        mid_v = (uv1.y + uv2.y) / 2
                        sx, sy = uv_to_region(mid_u, mid_v)

                        # Calculamos distancia contra el ÚLTIMO CLIC
                        dist_target = ((sx - target_x)**2 + (sy - target_y)**2)**0.5
                        
                        px_dist = ((uv1.x - uv2.x) * tex_w)**2 + ((uv1.y - uv2.y) * tex_h)**2
                        px_len = px_dist**0.5
                        if px_len < 0.1: continue
                        text = f"{px_len:.1f}px"

                        unique_id = (obj.name, 'EDGE', l_curr.edge.index)
                        if unique_id not in candidates: candidates[unique_id] = []
                        candidates[unique_id].append( (dist_target, sx, sy, text) )

            # --- RECOLECTAR CARAS ---
            if show_faces:
                for face in bm.faces:
                    is_face_selected = False
                    if use_sync:
                        if face.select: is_face_selected = True
                    else:
                        loops_uv = [l[uv_layer] for l in face.loops]
                        if all(l.select for l in loops_uv): is_face_selected = True
                    
                    if not is_face_selected: continue

                    uvs = [l[uv_layer].uv for l in face.loops]
                    if not uvs: continue
                    
                    min_u, max_u = min(u.x for u in uvs), max(u.x for u in uvs)
                    min_v, max_v = min(u.y for u in uvs), max(u.y for u in uvs)
                    
                    w_px = (max_u - min_u) * tex_w
                    h_px = (max_v - min_v) * tex_h

                    cx_center, cy_center = uv_to_region((min_u + max_u)/2, (min_v + max_v)/2)
                    dist_target = ((cx_center - target_x)**2 + (cy_center - target_y)**2)**0.5

                    cx_w, cy_w = uv_to_region((min_u + max_u)/2, min_v)
                    cx_h, cy_h = uv_to_region(min_u, (min_v + max_v)/2)

                    unique_id = (obj.name, 'FACE', face.index)
                    if unique_id not in candidates: candidates[unique_id] = []
                    candidates[unique_id].append( (dist_target, cx_w, cy_w, cx_h, cy_h, w_px, h_px) )

        except Exception:
            continue
        finally:
            if bm: bm.free()

    # --- DIBUJADO FINAL ---
    for uid, locations in candidates.items():
        # Ordenamos por cercanía al último clic
        locations.sort(key=lambda x: x[0])
        best_match = locations[0]
        
        if uid[1] == 'EDGE':
            _, sx, sy, text = best_match
            blf.position(font_id, sx, sy, 0)
            blf.draw(font_id, text)
            
        elif uid[1] == 'FACE':
            _, cx_w, cy_w, cx_h, cy_h, w_px, h_px = best_match
            blf.position(font_id, cx_w, cy_w - 20, 0)
            blf.draw(font_id, f"W: {w_px:.1f}")
            blf.position(font_id, cx_h - 50, cy_h, 0)
            blf.draw(font_id, f"H: {h_px:.1f}")

class OPS_OT_ToggleUVMeasures(bpy.types.Operator):
    """Activa medidas UV, Sync, Modo Caras y Selecciona Todo"""
    bl_idname = "hytale.toggle_uv_measures"
    bl_label = "Ver Medidas UV (Full Setup)"
    
    def force_uv_redraw(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    area.tag_redraw()
    
    def modal(self, context, event):
        global uv_measures_running, last_click_abs_x, last_click_abs_y, draw_handle_uv_stats
        
        if not uv_measures_running:
            if draw_handle_uv_stats:
                bpy.types.SpaceImageEditor.draw_handler_remove(draw_handle_uv_stats, 'WINDOW')
                draw_handle_uv_stats = None
            
            context.scene.hytale_uv_active = False
            self.force_uv_redraw(context)
            return {'FINISHED'}
        
        # --- COMPORTAMIENTO: SOLO CLIC ---
        is_action = False
        if event.type in {'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE'} and event.value == 'PRESS':
            is_action = True
        elif event.type not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'TIMER', 'TIMER_REPORT'} and event.value == 'PRESS':
            is_action = True
            
        if is_action:
            last_click_abs_x = event.mouse_x
            last_click_abs_y = event.mouse_y
            self.force_uv_redraw(context)
            
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        global uv_measures_running, draw_handle_uv_stats, last_click_abs_x, last_click_abs_y
        
        if uv_measures_running:
            uv_measures_running = False
            self.report({'INFO'}, "Medidas UV: DESACTIVADO")
            return {'FINISHED'}
        else:
            uv_measures_running = True
            context.scene.hytale_uv_active = True
            
            # ---------------------------------------------------------
            # CONFIGURACIÓN AUTOMÁTICA (FULL COMBO)
            # ---------------------------------------------------------
            
  
            
            # 1. Asegurar Modo Edición
            if context.active_object and context.active_object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # 2. ACTIVAR UV SYNC (¡Lo nuevo!)
            context.scene.tool_settings.use_uv_select_sync = True
            
            # 3. Cambiar a MODO CARAS
            # Como Sync está activo, controlamos la selección 3D
            context.tool_settings.mesh_select_mode = (False, False, True) 
            
            # 4. Seleccionar TODO
            try:
                bpy.ops.mesh.select_all(action='SELECT')
            except:
                pass
            
            # ---------------------------------------------------------

            last_click_abs_x = event.mouse_x
            last_click_abs_y = event.mouse_y

            draw_handle_uv_stats = bpy.types.SpaceImageEditor.draw_handler_add(
                draw_uv_stats_callback, (self, context), 'WINDOW', 'POST_PIXEL')
            
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'}, "Medidas UV: LISTO (Sync + Caras + Todo)")
            self.force_uv_redraw(context)
            
            return {'RUNNING_MODAL'}
            
class OPS_OT_DetectTexture(bpy.types.Operator):
    """Detecta una textura del material activo y la asigna"""
    bl_idname = "hytale.detect_texture"
    bl_label = "Detectar Textura del Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.hytale_props
        obj = context.active_object
        
        if not obj or not obj.active_material:
            self.report({'WARNING'}, "No hay material activo")
            return {'CANCELLED'}
            
        mat = obj.active_material
        if not mat.use_nodes:
            self.report({'WARNING'}, "El material no usa nodos")
            return {'CANCELLED'}
            
        # Buscar el primer nodo de imagen con una imagen asignada
        found_image = None
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                found_image = node.image
                break
        
        if found_image:
            props.target_image = found_image
            self.report({'INFO'}, f"Textura detectada: {found_image.name}")
        else:
            self.report({'WARNING'}, "No se encontró ninguna textura en el material")
            
        return {'FINISHED'}

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.39"
    bl_idname = "VIEW3D_PT_hytale_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hytale'

    def draw(self, context):
        layout = self.layout
        props = context.scene.hytale_props
        
                
        # 0. DIAGNÓSTICO (Restaurado)
        draw_validator_ui(self, context, layout)
        
        #1. IMPORTACIÓN (Siempre visible)
        box = layout.box()
        box.label(text="Importar (Blockymodel):", icon='IMPORT')
        row = box.row()
        box.operator("hytale.import_model", icon='FILE_FOLDER', text="Cargar Modelo")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Utilidades & Referencias:", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.prop(props, "selected_reference", text="")
        row.operator("hytale.load_reference", icon='IMPORT', text="Cargar")
        
        layout.separator()
        
        # 2. CONFIGURACIÓN GENERAL (Setup)
        box_main = layout.box()
        box_main.label(text="Configuración de Escena", icon='PREFERENCES')
        box_main.separator()
        
        # SELECCIÓN DE COLECCIÓN (El interruptor principal)
        box_main.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
        has_collection = props.target_collection is not None
        if not has_collection:
            box_main.label(text="¡Selecciona colección para editar!", icon='INFO')
        row = box_main.row(align=True)
        box_main.prop(props, "setup_pixel_grid", text="Modo Pixel Perfect")
        if props.setup_pixel_grid:
            col_main = box_main.column()
            col_main.prop(props, "show_subdivisions", icon='GRID')

        box_main.separator()
        
        layout.separator()

        # 3. MATERIAL Y TEXTURA (El nuevo núcleo)
        box_mat = layout.box()
        box_mat.label(text="Material y Textura", icon='MATERIAL')
        box_mat.enabled = has_collection # Bloqueo visual si no hay colección
        
        col = box_mat.column(align=True)
        col.template_ID(props, "target_material", new="material.new")
        
        if props.target_material:
            col.separator()
            row = col.row(align=True)
            # template_ID para Textura (Nueva/Abrir/Seleccionar)
            row.template_ID(props, "target_image", new="image.new", open="image.open")
            
            # Botón de re-detección manual
            row.operator("hytale.detect_texture", icon='EYEDROPPER', text="")
            
            if props.target_image:
                row = col.row()
                row.alignment = 'CENTER'
                row.label(text=f"{props.target_image.size[0]} x {props.target_image.size[1]} px", icon='CHECKMARK')
        else:
            col.label(text="Selecciona Material Unificado", icon='ERROR')

        layout.separator()

        # --- Herramientas UV ---
        box = layout.box()
        box.label(text="Herramientas UV:", icon='UV_DATA')
        box.prop(props, "new_unwrap")
        box.prop(props, "auto_stack", text="Auto Stack Similar UV Islands")
        box.operator("hytale.pixel_perfect_pack", icon='UV_SYNC_SELECT', text="Pixel Perfect Pack")
        
        is_active = context.scene.hytale_uv_active
        box.operator("hytale.toggle_uv_measures", icon="DRIVER_DISTANCE", text="Mostrar Medidas En UV's", depress=is_active)
        
        layout.separator()

        # 6. EXPORTACIÓN
        box_exp = layout.box()
        box_exp.label(text="Exportación", icon='EXPORT')
        box_exp.enabled = has_collection and (props.target_material is not None)
        
        col_exp = box_exp.column()
        col_exp.prop(props, "file_path", text="") # Restaurado path manual
        
        row = col_exp.row()
        row.scale_y = 1.5
        row.operator("hytale.export_model", icon='CHECKMARK', text="EXPORTAR MODELO")

classes = (HytaleProperties, OPS_OT_SetupHytaleScene, OPS_OT_LoadReference, OPS_OT_ExportHytale, OPS_OT_ImportHytale, PT_HytalePanel, OPS_OT_DetectTexture, OPS_OT_PixelPerfectPack, OPS_OT_ToggleUVMeasures)

def register():
    bpy.types.Scene.hytale_uv_active = bpy.props.BoolProperty(default=False)
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.hytale_props = bpy.props.PointerProperty(type=HytaleProperties)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hytale_props
    del bpy.types.Scene.hytale_uv_active

if __name__ == "__main__": register()
