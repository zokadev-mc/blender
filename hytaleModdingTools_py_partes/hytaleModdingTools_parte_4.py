# PARTE 4/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES


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
        
# -------------------------
# Operator: Pixel Perfect + Constrain to Image Bounds
# -------------------------
class OPS_OT_PixelPerfectPack(bpy.types.Operator):
    bl_idname = "hytale.pixel_perfect_pack"
    bl_label = "Scale UV's To Pixel Perfect"
    bl_description = "Escala UVs a pixel-perfect y restringe la selección completa al lienzo 0..1 (no por-isla)."

    def execute(self, context):
        # Props & fallbacks
        props = getattr(context.scene, "hytale_props", None)
        if not props:
            class _P:
                new_unwrap = True
                snap_uvs = True
            props = _P()

        def safe_get_image_size(objs):
            try:
                return get_image_size_from_objects(objs)
            except Exception:
                return 32, 32

        def round_px(val_px):
            return math.floor(val_px + 0.5)

        def constrain_uvs_to_bounds(uvs):
            """
            Intenta meter las UVs en 0..1. 
            IMPORTANTE: Si el bloque de UVs es más grande que 1.0 (tiling), 
            se aborta la operación para no romper la densidad de píxeles.
            """
            if not uvs:
                return

            min_u = min(uv.x for uv in uvs)
            max_u = max(uv.x for uv in uvs)
            min_v = min(uv.y for uv in uvs)
            max_v = max(uv.y for uv in uvs)
            
            width = max_u - min_u
            height = max_v - min_v
            eps = 1e-5 # Un margen pequeño pero seguro

            # 1. CHECK DE TAMAÑO (La corrección principal)
            # Si el bounding box total es mayor que el espacio 0..1,
            # significa que necesitamos tiling. No restringimos.
            if width > 1.0 + eps or height > 1.0 + eps:
                return

            # 2. Traslación (Shift) para meter bbox en 0..1 si cabe
            # (No escalamos, solo movemos si se sale un poco pero cabe)
            shift_u = 0.0
            if min_u < 0.0:
                shift_u = -min_u
            elif max_u > 1.0:
                shift_u = 1.0 - max_u
            
            shift_v = 0.0
            if min_v < 0.0:
                shift_v = -min_v
            elif max_v > 1.0:
                shift_v = 1.0 - max_v
            
            if shift_u != 0.0 or shift_v != 0.0:
                for uv in uvs:
                    uv.x += shift_u
                    uv.y += shift_v

        # -------------------------
        # Inicio operator
        # -------------------------
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not selected_meshes:
            self.report({'WARNING'}, "Selecciona al menos un objeto Mesh")
            return {'CANCELLED'}

        tex_w, tex_h = safe_get_image_size(selected_meshes)
        pixels_per_meter = 16.0
        eps = 1e-8

        bpy.ops.object.mode_set(mode='EDIT')

        # Construir bmesh por objeto y lista global de faces
        bm_map = {}
        all_faces = []
        for obj in selected_meshes:
            bm = bmesh.from_edit_mesh(obj.data)
            if not bm.loops.layers.uv:
                bm.loops.layers.uv.new()
            bm.loops.layers.uv.verify()
            bm_map[obj] = bm
            for f in bm.faces:
                all_faces.append((f, bm))

        if not all_faces:
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}

        # Pre-unwrap / align si corresponde
        bpy.ops.mesh.select_all(action='SELECT')
        if props.new_unwrap:
            try:
                bpy.ops.uv.unwrap(method='CONFORMAL', margin=0.001)
            except Exception:
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)

        # Cara dominante (usar para cálculo de escala uniforme)
        dom_face, dom_bm = max(all_faces, key=lambda it: it[0].calc_area())
        uv_layer_active = dom_bm.loops.layers.uv.active

        vec_3d_1 = dom_face.loops[1].vert.co - dom_face.loops[0].vert.co
        vec_3d_2 = dom_face.loops[-1].vert.co - dom_face.loops[0].vert.co
        len_3d_1 = vec_3d_1.length
        len_3d_2 = vec_3d_2.length

        uv0 = dom_face.loops[0][uv_layer_active].uv.copy()
        uv1 = dom_face.loops[1][uv_layer_active].uv.copy()
        uv3 = dom_face.loops[-1][uv_layer_active].uv.copy()
        vec_uv_1 = uv1 - uv0
        vec_uv_2 = uv3 - uv0

        is_uv1_horizontal = abs(vec_uv_1.x) >= abs(vec_uv_1.y)

        def comp_len(vec, axis):
            if axis == 'x':
                return abs(vec.x) if abs(vec.x) > eps else vec.length
            else:
                return abs(vec.y) if abs(vec.y) > eps else vec.length

        if is_uv1_horizontal:
            target_uv_len_u = (len_3d_1 * pixels_per_meter) / float(tex_w)
            target_uv_len_v = (len_3d_2 * pixels_per_meter) / float(tex_h)
            curr_uv_len_u = comp_len(vec_uv_1, 'x')
            curr_uv_len_v = comp_len(vec_uv_2, 'y')
        else:
            target_uv_len_v = (len_3d_1 * pixels_per_meter) / float(tex_h)
            target_uv_len_u = (len_3d_2 * pixels_per_meter) / float(tex_w)
            curr_uv_len_v = comp_len(vec_uv_1, 'y')
            curr_uv_len_u = comp_len(vec_uv_2, 'x')

        if 'curr_uv_len_u' not in locals():
            curr_uv_len_u = comp_len(vec_uv_1, 'x') if is_uv1_horizontal else comp_len(vec_uv_2, 'x')
        if 'curr_uv_len_v' not in locals():
            curr_uv_len_v = comp_len(vec_uv_2, 'y') if is_uv1_horizontal else comp_len(vec_uv_1, 'y')

        scale_u = target_uv_len_u / (curr_uv_len_u if curr_uv_len_u > eps else eps)
        scale_v = target_uv_len_v / (curr_uv_len_v if curr_uv_len_v > eps else eps)

        # ---------- APLICAR ESCALA A TODAS LAS UVs ----------
        # recolectar lista global de referencias a UVs (mantener orden por objeto para update)
        global_uvs = []
        per_obj_uvs = {}  # obj -> list(uv refs)
        for obj, bm in bm_map.items():
            uv_layer = bm.loops.layers.uv.active
            uvs = [loop[uv_layer].uv for face in bm.faces for loop in face.loops]
            per_obj_uvs[obj] = uvs
            global_uvs.extend(uvs)

        # Aplicar scale uniforme a cada UV (manteniendo su offset relativo)
        for uv in global_uvs:
            uv.x *= scale_u
            uv.y *= scale_v

        # ---------- SNAP GLOBAL (si está activado): mantener posiciones relativas ----------
        if props.snap_uvs and global_uvs:
            min_u_px = min((uv.x * tex_w) for uv in global_uvs)
            min_v_px = min((uv.y * tex_h) for uv in global_uvs)
            target_min_u_px = round_px(min_u_px)
            target_min_v_px = round_px(min_v_px)
            delta_u = (target_min_u_px - min_u_px) / float(tex_w)
            delta_v = (target_min_v_px - min_v_px) / float(tex_h)
            # aplicar traslación global coherente
            for uv in global_uvs:
                uv.x += delta_u
                uv.y += delta_v
            # luego redondeo por UV a píxel
            for uv in global_uvs:
                uv.x = round_px(uv.x * tex_w) / float(tex_w)
                uv.y = round_px(uv.y * tex_h) / float(tex_h)

        # ---------- Constrain global: Solo si cabe en la textura ----------
        constrain_uvs_to_bounds(global_uvs)

        # ---------- Actualizaciones por objeto ----------
        for obj, bm in bm_map.items():
            # NOTA: Se eliminó el bucle de "clamp" que forzaba 0..1 y deformaba los bordes.
            bmesh.update_edit_mesh(obj.data)

        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, "Pixel Perfect aplicado (Tiling permitido).")
        return {'FINISHED'}
        
# --- VARIABLES DE CONTROL ---
_last_processed_mat = None
_is_updating = False

def get_collection_meshes(props):
    """Obtiene todos los objetos MESH de la colección seleccionada."""
    if props.target_collection:
        return [obj for obj in props.target_collection.objects if obj.type == 'MESH']
    return []

def update_material_texture(self, context):
    """
    Gestor Directo:
    - Si target_image es None -> CORTAR CABLES (Remove Link).
    - Si target_image es Imagen -> CONECTAR CABLES.
    """
    global _last_processed_mat, _is_updating
    
    if _is_updating: return

    mat = self.target_material
    
    # 1. OBTENER OBJETOS
    target_meshes = get_collection_meshes(self)
    
    # 2. APLICAR MATERIAL A LA COLECCIÓN
    if target_meshes:
        for obj in target_meshes:
            if mat:
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                elif obj.active_material != mat:
                    obj.active_material = mat
            else:
                if obj.data.materials:
                    obj.data.materials.clear()

    if not mat:
        _last_processed_mat = None
        if self.target_image is not None:
             self.target_image = None
        return

    # 3. PREPARAR NODOS
    if not mat.use_nodes: mat.use_nodes = True
    tree = mat.node_tree
    bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf: return

    # --- FASE 1: DETECTAR SI CAMBIAMOS DE MATERIAL (PULL) ---
    if mat != _last_processed_mat:
        _last_processed_mat = mat
        _is_updating = True
        try:
            # Leemos qué tiene conectado el material nuevo
            tex_image = None
            if bsdf.inputs['Base Color'].is_linked:
                # Obtenemos el nodo conectado
                node = bsdf.inputs['Base Color'].links[0].from_node
                if node.type == 'TEX_IMAGE':
                    tex_image = node.image
            
            if self.target_image != tex_image:
                self.target_image = tex_image
        finally:
            _is_updating = False
        return

    # --- FASE 2: ACCIÓN DEL USUARIO (PUSH) ---
    
    # CASO A: EL USUARIO PULSÓ LA X (UNLINK DIRECTO)
    if self.target_image is None:
        # 1. Desconectar Color (Directo, sin preguntar)
        if bsdf.inputs['Base Color'].is_linked:
            link = bsdf.inputs['Base Color'].links[0]
            tree.links.remove(link) # <--- AQUÍ ESTÁ EL REMOVE LINK PURO
        
        # 2. Desconectar Alfa (Directo)
        if 'Alpha' in bsdf.inputs and bsdf.inputs['Alpha'].is_linked:
            link = bsdf.inputs['Alpha'].links[0]
            tree.links.remove(link) # <--- AQUÍ TAMBIÉN
        
        # 3. Actualizar Viewport inmediatamente
        for obj in target_meshes:
            obj.update_tag()
            
        # Forzar redibujado de la UI
        context.area.tag_redraw()
        return

    # CASO B: ASIGNAR TEXTURA (CONECTAR)
    # Buscamos o creamos el nodo
    tex_node = next((n for n in tree.nodes if n.type == 'TEX_IMAGE'), None)
    if not tex_node:
        tex_node = tree.nodes.new('ShaderNodeTexImage')
        tex_node.location = (-300, 300)

    # Asignamos imagen
    if tex_node.image != self.target_image:
        tex_node.image = self.target_image
    
    # Aseguramos conexión Color
    if not bsdf.inputs['Base Color'].is_linked:
        tree.links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
    elif bsdf.inputs['Base Color'].links[0].from_node != tex_node:
        # Si hay algo conectado que NO es nuestro nodo, lo reemplazamos
        tree.links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
    
    # Aseguramos conexión Alfa
    if 'Alpha' in bsdf.inputs:
        if not bsdf.inputs['Alpha'].is_linked:
             tree.links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
    
    for obj in target_meshes:
        obj.update_tag()
        
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
        update=update_material_texture
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
