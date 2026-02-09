# PARTE 3/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES


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

# Añadimos un argumento nuevo al final: inherited_offset
def process_node_import(node_data, parent_obj, texture_width, texture_height, collection, inherited_offset=None):
    if inherited_offset is None:
        inherited_offset = mathutils.Vector((0, 0, 0))

    name = node_data.get("name", "Node")
    
    # 1. Posición base (La que dice el archivo)
    raw_pos = node_data.get("position", {})
    pos = hytale_to_blender_pos(raw_pos)
    rot = hytale_to_blender_quat(node_data.get("orientation", {}))
    
    # --- APLICAR LA CORRECCIÓN SOLO AL NODO ACTUAL (HIJO) ---
    # Sumamos el offset que nos mandó el padre (si hubo alguno)
    # El padre no se mueve, pero el hijo nace desplazado para coincidir con la malla del padre.
    final_pos = pos + inherited_offset

    # --- 2. CREAR EL NODO (PIVOTE) ---
    node_empty = bpy.data.objects.new(name, None)
    node_empty.empty_display_type = 'PLAIN_AXES'
    node_empty.empty_display_size = 0.2
    collection.objects.link(node_empty)
    
    # Usamos la posición corregida
    node_empty.location = final_pos
    node_empty.rotation_mode = 'QUATERNION'
    node_empty.rotation_quaternion = rot
    
    if parent_obj:
        node_empty.parent = parent_obj
    
    # --- 3. PREPARAR EL OFFSET PARA MIS PROPIOS HIJOS ---
    # Leemos si este nodo actual tiene un offset visual (shape.offset)
    shape_data = node_data.get("shape", {})
    raw_shape_offset = shape_data.get("offset", {'x': 0, 'y': 0, 'z': 0})
    current_node_visual_offset = hytale_to_blender_pos(raw_shape_offset)
    
    # --- 4. CREAR LA MESH ---
    # (Tu lógica de creación de mesh se mantiene casi igual, 
    #  pero asegurándonos de aplicar el offset visual A LA MALLA localmente)
    
    shape_type = shape_data.get("type", "none")
    if shape_type != "none":
        st = shape_data.get("stretch", {'x': 1.0, 'y': 1.0, 'z': 1.0})
        
        # Aquí SÍ usamos el offset normal en la malla, porque el pivote de ESTE nodo 
        # no se ha movido por su propio offset, sino por el del padre.
        # Por tanto, la malla necesita su propio offset local.
        if shape_type == 'box':
            mesh = create_mesh_box_import(name, shape_data, texture_width, texture_height)
        else:
            mesh = create_mesh_quad_import(name, shape_data, texture_width, texture_height)
            
        mesh_obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(mesh_obj)
        mesh_obj.parent = node_empty
        mesh_obj.scale = (st.get('x', 1.0), st.get('z', 1.0), st.get('y', 1.0))

    # --- 5. PROCESAR HIJOS RECURSIVAMENTE ---
    children_list = node_data.get("children", [])
    for child in children_list:
        # AQUÍ ESTÁ LA MAGIA:
        # Pasamos el 'current_node_visual_offset' a los hijos.
        # Si este nodo (Handle) tenía un offset de 5, el hijo (Hammer) recibirá ese 5
        # y se sumará a su posición.
        process_node_import(child, node_empty, texture_width, texture_height, collection, inherited_offset=current_node_visual_offset)
        
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
                "textureHeight": int(tex_h), 
                "lod": "auto"
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
