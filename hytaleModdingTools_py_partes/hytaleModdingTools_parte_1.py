# PARTE 1/5 - hytaleModdingTools.py
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
    return int(math.floor(n + 0.50001))

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
    no_texture_connected_objs = []  # <-- nuevo: objetos cuyo material no tiene textura conectada
    
    for obj in collection.objects:
        if obj.type == 'MESH':
            # Checks
            if obj.scale.x < 0 or obj.scale.y < 0 or obj.scale.z < 0:
                negative_scale_objs.append(obj.name)
            if not obj.data.materials:
                no_mat_objs.append(obj.name)
            if len(obj.data.vertices) > 8:
                complex_objs.append(obj.name)
            if obj.parent and obj.parent.type == 'MESH':
                mesh_parent_mesh_objs.append(obj.name)

            # Check: textura conectada al material (si tiene materiales)
            has_texture = False
            if obj.data.materials:
                # Recorremos todos los materiales asignados y consideramos OK si cualquiera tiene textura conectada
                for mat in obj.data.materials:
                    if not mat:
                        continue
                    if mat.use_nodes and mat.node_tree:
                        # Buscar BSDF principled(s)
                        bsdfs = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
                        # Si no hay Principled, intentar detectar ImageTexture link a cualquier socket llamado "Base Color"
                        if bsdfs:
                            for bsdf in bsdfs:
                                for link in mat.node_tree.links:
                                    if link.to_node == bsdf and link.to_socket.name == 'Base Color':
                                        # desde qué nodo viene el link
                                        from_node = link.from_node
                                        if getattr(from_node, "image", None) is not None:
                                            has_texture = True
                                            break
                                if has_texture:
                                    break
                        else:
                            # Fallback: buscar Image Texture con imagen y que tenga links salientes
                            for node in mat.node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and getattr(node, "image", None) is not None:
                                    # comprobar si ese nodo está conectado a algo (me interesa que vaya al BSDF)
                                    for link in mat.node_tree.links:
                                        if link.from_node == node:
                                            # si enlaza a algo, asumimos que se usa como textura
                                            has_texture = True
                                            break
                                    if has_texture:
                                        break
                    if has_texture:
                        break

            # Si tiene material(s) pero ninguna textura conectada -> reportar
            if obj.data.materials and not has_texture:
                no_texture_connected_objs.append(obj.name)

    # Siblings check (mantengo tu lógica: detecta múltiples hijos compartiendo el mismo parent cuando el parent NO es mesh)
    siblings_issue = False
    parent_map = {}
    for obj in collection.objects:
        if obj.parent and obj.type == 'MESH':
            if obj.parent.type != 'MESH':
                if obj.parent.name not in parent_map:
                    parent_map[obj.parent.name] = 0
                parent_map[obj.parent.name] += 1
                if parent_map[obj.parent.name] > 1:
                    siblings_issue = True

    # Render
    if complex_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True 
        col.label(text="Geometría Compleja (ERROR):", icon='CANCEL')
        col.label(text="(Modelo con vertices > 8 detectado.)", icon='BLANK1')
        for name in complex_objs[:5]:
            col.label(text=f"• {name}", icon='MESH_DATA')
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
        for name in negative_scale_objs[:3]:
            col.label(text=f"• {name}")
        col.separator()

    if no_mat_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True
        col.label(text="Falta Material/Textura:", icon='MATERIAL')
        for name in no_mat_objs[:3]:
            col.label(text=f"• {name}")
        col.separator()

    # Nuevo bloque: materiales presentes pero sin textura conectada al Base Color
    if no_texture_connected_objs:
        issues_found = True
        col = box.column(align=True)
        col.alert = True
        col.label(text="Textura no conectada al material:", icon='ERROR')
        col.label(text="ACCIÓN: Conecta una Image Texture al Base Color del Principled BSDF.", icon='NODE_TEXTURE')
        for name in no_texture_connected_objs[:5]:
            col.label(text=f"• {name}", icon='MESH_DATA')
        col.separator()

    if siblings_issue:
        issues_found = True  # CORREGIDO: antes estaba en False y anulaba otros issues
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
