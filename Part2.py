def create_mesh_quad_import(name, shape_data, texture_width, texture_height):
    settings = shape_data.get("settings", {})
    size = settings.get("size", {})
    n = settings.get("normal", "+Y")
    dx, dy = size.get('x', 16)/32.0, size.get('y', 16)/32.0
    bm = bmesh.new()

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
    shape_data = node_data.get("shape", {})
    shape_type = shape_data.get("type", "none")
    
    obj = None
    if shape_type == 'box':
        mesh = create_mesh_box_import(name, shape_data, texture_width, texture_height)
        obj = bpy.data.objects.new(name, mesh)
    elif shape_type == 'quad':
        mesh = create_mesh_quad_import(name, shape_data, texture_width, texture_height)
        obj = bpy.data.objects.new(name, mesh)
    else:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = 'PLAIN_AXES'
    
    collection.objects.link(obj)
    obj.location = pos
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = rot
    if parent_obj: obj.parent = parent_obj
        
    for child in node_data.get("children", []):
        process_node_import(child, obj, texture_width, texture_height, collection)
    return obj

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
        col_name = props.collection_name
        issues_found = False
        
        # Validación rápida de seguridad
        if col_name in bpy.data.collections:
            collection = bpy.data.collections[col_name]
            for obj in collection.objects:
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
        source_col_name = props.collection_name
        
        if source_col_name not in bpy.data.collections:
            self.report({'ERROR'}, f"Colección '{source_col_name}' no encontrada")
            return {'CANCELLED'}
            
        output_path = bpy.path.abspath(props.file_path)
        if not output_path:
            self.report({'ERROR'}, "Ruta de archivo no definida.")
            return {'CANCELLED'}
        if not output_path.lower().endswith(".blockymodel"): output_path += ".blockymodel"
        
        # --- LÓGICA DE TEXTURA / RESOLUCIÓN ---
        tex_w, tex_h = 64, 64 # Valor por defecto seguro
        
        if props.resolution_mode == 'IMAGE':
            if props.target_image:
                tex_w = props.target_image.size[0]
                tex_h = props.target_image.size[1]
            else:
                self.report({'WARNING'}, "Modo Textura activado pero sin imagen. Usando 64x64.")
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
            processed_roots = process_and_decompose_collection(bpy.data.collections[source_col_name], temp_col)
            
            id_counter = [0]
            # Pasamos las dimensiones (tex_w, tex_h) calculadas arriba
            nodes_array = [process_node(root, tex_w, tex_h, props.snap_uvs, id_counter) for root in processed_roots]
            
            final_json = { 
                "nodes": nodes_array, 
                "format": "character", 
                "textureWidth": int(tex_w), 
                "textureHeight": int(tex_h) 
            }
            
            json_str = json.dumps(final_json, indent=4)
            # Limpieza visual de vectores (opcional)
            json_str = re.sub(r'\{\s+"x":\s*([^{}\[\]]+?),\s+"y":\s*([^{}\[\]]+?),\s+"z":\s*([^{}\[\]]+?)\s+\}', r'{"x": \1, "y": \2, "z": \3}', json_str)

            with open(output_path, 'w') as f:
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

class OPS_OT_ImportHytale(bpy.types.Operator, ImportHelper):
    bl_idname = "hytale.import_model"
    bl_label = "Seleccionar .blockymodel"
    filename_ext = ".blockymodel"
    filter_glob: bpy.props.StringProperty(default="*.blockymodel;*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, 'r') as f: data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}
            
        model_name = os.path.splitext(os.path.basename(self.filepath))[0]
        col = bpy.data.collections.new(model_name)
        context.scene.collection.children.link(col)
        
        tex_w = data.get("textureWidth", 64)
        tex_h = data.get("textureHeight", 64)
        tex_path = os.path.splitext(self.filepath)[0] + ".png"
        material = setup_import_material(tex_path, tex_w, tex_h)
        
        bpy.ops.object.select_all(action='DESELECT')
        for node in data.get("nodes", []):
            root_obj = process_node_import(node, None, tex_w, tex_h, col)
            if root_obj:
                for o in [root_obj] + [c for c in root_obj.children_recursive]:
                    if o.type == 'MESH':
                        if not o.data.materials: o.data.materials.append(material)
                        else: o.data.materials[0] = material
        
        self.report({'INFO'}, f"Importado: {model_name}")
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
        if not tex_w: tex_w, tex_h = 64, 64 

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


def update_target_texture(self, context):
    """
    Callback: Cuando se selecciona una imagen en el panel,
    esta función la aplica automáticamente al material de los objetos.
    """
    target_img = self.target_image
    col_name = self.collection_name
    
    # Validaciones básicas
    if not target_img: return
    if col_name not in bpy.data.collections: return
        
    collection = bpy.data.collections[col_name]
    
    for obj in collection.objects:
        if obj.type == 'MESH':
            # 1. Obtener o crear material
            if not obj.data.materials:
                mat = bpy.data.materials.new(name=f"Hytale_{col_name}_Mat")
                obj.data.materials.append(mat)
            else:
                mat = obj.data.materials[0]
            
            # 2. Activar nodos
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # 3. Buscar el nodo Principled BSDF
            bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            
            # Si el material está vacío o roto, lo reconstruimos
            if not bsdf:
                nodes.clear()
                bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                bsdf.location = (0, 0)
                out = nodes.new('ShaderNodeOutputMaterial')
                out.location = (300, 0)
                links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
            
            # 4. Configurar el nodo de Textura
            tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
            if not tex_node:
                tex_node = nodes.new('ShaderNodeTexImage')
                tex_node.location = (-300, 200)
            
            # Asignar la imagen seleccionada
            tex_node.image = target_img
            tex_node.interpolation = 'Closest' # Importante para Pixel Art/Minecraft style
            
            # 5. Conectar al Base Color y Alpha
            if 'Base Color' in bsdf.inputs:
                links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
            
            if 'Alpha' in bsdf.inputs:
                links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
                # Activar transparencia en el material para viewport
                mat.blend_method = 'CLIP'
                mat.shadow_method = 'CLIP'

# --- UI Y PANEL ---

class HytaleProperties(bpy.types.PropertyGroup):
    collection_name: bpy.props.StringProperty(
        name="Colección",
        description="Nombre de la colección a exportar",
        default="Collection"
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
        default=64,
        min=1
    )
    tex_height: bpy.props.IntProperty(
        name="Alto (H)",
        default=64,
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

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.3"
    bl_idname = "VIEW3D_PT_hytale_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hytale'

    def draw(self, context):
        layout = self.layout
        props = context.scene.hytale_props
        
        box = layout.box()
        box.label(text="Importar (Blockymodel):", icon='IMPORT')
        box.operator("hytale.import_model", icon='FILE_FOLDER', text="Cargar Modelo")
        
        layout.separator()
        
        
        box = layout.box()
        box.label(text="Utilidades & Referencias:", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.prop(props, "selected_reference", text="")
        row.operator("hytale.load_reference", icon='IMPORT', text="Cargar")
        
        layout.separator()
        
        # --- Configuración y Referencias ---
        box = layout.box()
        box.label(text="Configuración:", icon='PREFERENCES')
        box.prop(props, "setup_pixel_grid", text="Modo Pixel Perfect")
        if props.setup_pixel_grid:
            col = box.column()
            col.prop(props, "show_subdivisions", icon='GRID')
        
        layout.separator()
        draw_validator_ui(self, context, layout) # Tu función de diagnóstico
        
        layout.separator()
        
        # --- Herramientas UV ---
        box = layout.box()
        box.label(text="Herramientas UV:", icon='UV_DATA')
        box.prop(props, "new_unwrap")
        box.prop(props, "auto_stack", text="Auto Stack Similar UV Islands")
        box.operator("hytale.pixel_perfect_pack", icon='UV_SYNC_SELECT', text="Pixel Perfect Pack")
        
        layout.separator()
        
        # --- EXPORTACIÓN Y TEXTURAS (Aquí está el cambio) ---
        box = layout.box()
        box.label(text="Exportación:", icon='EXPORT')
        col = box.column(align=True)
        col.prop(props, "collection_name")
        
        col.separator()
        col.label(text="Definición de UVs:", icon='TEXTURE')
        
        # Selector de Modo (Botones)
        col.prop(props, "resolution_mode", expand=True)
        
        if props.resolution_mode == 'IMAGE':
            # Interfaz Modo Imagen
            box_inner = col.box()
            box_inner.label(text="Selecciona la Skin:", icon='IMAGE_DATA')
            box_inner.template_ID(props, "target_image", open="image.open")
            
            if props.target_image:
                row = box_inner.row()
                row.alignment = 'CENTER'
                row.label(text=f"Detectado: {props.target_image.size[0]} x {props.target_image.size[1]} px", icon='CHECKMARK')
            else:
                box_inner.label(text="¡Selecciona una imagen!", icon='ERROR')
        else:
            # Interfaz Modo Manual
            box_inner = col.box()
            box_inner.label(text="Lienzo Manual:", icon='EDITMODE_HLT')
            row = box_inner.row(align=True)
            row.prop(props, "tex_width")
            row.prop(props, "tex_height")

        col.separator()
        col.prop(props, "snap_uvs")
        col.prop(props, "file_path", text="")
        
        row = col.row()
        row.scale_y = 1.5
        row.operator("hytale.export_model", icon='CHECKMARK', text="EXPORTAR")

classes = (HytaleProperties, OPS_OT_SetupHytaleScene, OPS_OT_LoadReference, OPS_OT_ExportHytale, OPS_OT_ImportHytale, PT_HytalePanel, OPS_OT_PixelPerfectPack)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.hytale_props = bpy.props.PointerProperty(type=HytaleProperties)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hytale_props


if __name__ == "__main__": register()
