# PARTE 3/4 - hytaleModdingTools.py
# CAMBIOS RECIENTES

            
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
            
            # --- BLOQUE OPTIMIZADO: Formato Compacto ---
            # 1. Generamos JSON con indentación vertical limpia
            json_str = json.dumps(final_json, indent=1)
            
            # 2. OPTIMIZACIÓN: Colapsar vectores {x,y,z} en una sola línea
            # Convierte:
            # {
            #  "x": 10,
            #  "y": 5,
            #  "z": 0
            # }
            # a: {"x": 10, "y": 5, "z": 0}
            json_str = re.sub(
                r'\{\s*"x":\s*([\d\.-]+),\s*"y":\s*([\d\.-]+),\s*"z":\s*([\d\.-]+)\s*\}', 
                r'{"x": \1, "y": \2, "z": \3}', 
                json_str, 
                flags=re.DOTALL
            )
            
            # 3. OPTIMIZACIÓN: Colapsar Cuaterniones {x,y,z,w}
            json_str = re.sub(
                r'\{\s*"x":\s*([\d\.-]+),\s*"y":\s*([\d\.-]+),\s*"z":\s*([\d\.-]+),\s*"w":\s*([\d\.-]+)\s*\}', 
                r'{"x": \1, "y": \2, "z": \3, "w": \4}', 
                json_str, 
                flags=re.DOTALL
            )
            
            # 4. Escritura
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
        tex_w = int(self.res_w) if self.res_w != '0' else data.get("textureWidth", 64)
        tex_h = int(self.res_h) if self.res_h != '0' else data.get("textureHeight", 64)

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


def update_target_material(self, context):
    """
    Callback: Cuando seleccionas un material, se aplica automáticamente
    a TODOS los objetos de la colección seleccionada.
    """
    mat = self.target_material
    collection = self.target_collection
    
    if not collection or not mat: return
        
    for obj in collection.objects:
        if obj.type == 'MESH':
            # Asignar el material en la ranura 0 (o crearla)
            if not obj.data.materials:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat

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
        description="Selecciona la colección del modelo"
    )
    
    # --- NUEVO: Propiedad para el Material ---
    target_material: bpy.props.PointerProperty(
        name="Material Base",
        type=bpy.types.Material,
        description="Este material se aplicará a todo el modelo",
        update=update_target_material
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
