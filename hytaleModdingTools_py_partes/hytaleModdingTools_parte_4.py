# PARTE 4/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES


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
