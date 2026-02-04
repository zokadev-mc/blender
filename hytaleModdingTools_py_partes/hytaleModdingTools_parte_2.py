# PARTE 2/4 - hytaleModdingTools.py
# CAMBIOS RECIENTES

    
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
                wrapper_name = f"GRP_{child.name}"
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
    
    off_x = data.get("offset", {}).get("x", 0)
    off_y = data.get("offset", {}).get("y", 0)
    ang = data.get("angle", 0)
    
    box_w, box_h = (fh, fw) if ang in [90, 270] else (fw, fh)
    real_x, real_y = off_x, off_y
    
    if ang == 90:    real_x = off_x - box_w
    elif ang == 180: real_x = off_x - box_w; real_y = off_y - box_h
    elif ang == 270: real_y = off_y - box_h

    u0 = real_x / tex_w
    u1 = (real_x + box_w) / tex_w
    v0 = 1.0 - (real_y / tex_h)
    v1 = 1.0 - ((real_y + box_h) / tex_h)

    uv_coords = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    if ang == 90:    uv_coords = [uv_coords[3], uv_coords[0], uv_coords[1], uv_coords[2]]
    elif ang == 180: uv_coords = [uv_coords[2], uv_coords[3], uv_coords[0], uv_coords[1]]
    elif ang == 270: uv_coords = [uv_coords[1], uv_coords[2], uv_coords[3], uv_coords[0]]

    face.loops[3][uv_layer].uv = uv_coords[0] 
    face.loops[2][uv_layer].uv = uv_coords[1] 
    face.loops[1][uv_layer].uv = uv_coords[2] 
    face.loops[0][uv_layer].uv = uv_coords[3] 

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
    
    # --- 1. CREAR EL NODO PRINCIPAL (PADRE/PIVOTE) ---
    node_empty = bpy.data.objects.new(name, None)
    node_empty.empty_display_type = 'PLAIN_AXES'
    node_empty.empty_display_size = 0.2
    collection.objects.link(node_empty)
    
    node_empty.location = pos
    node_empty.rotation_mode = 'QUATERNION'
    node_empty.rotation_quaternion = rot
    
    if parent_obj: node_empty.parent = parent_obj
    
    # --- PRE-VERIFICACIÓN DE HIJOS ---
    children_list = node_data.get("children", [])
    has_children = len(children_list) > 0

    # --- 2. CREAR LA FORMA (MESH) ---
    shape_data = node_data.get("shape", {})
    shape_type = shape_data.get("type", "none")
    
    if shape_type != "none":
        st = shape_data.get("stretch", {'x': 1.0, 'y': 1.0, 'z': 1.0})
        
        # Lógica para jerarquía avanzada (Padre -> Wrapper -> Malla)
        if has_children:
            # 1. Crear copia de shape SIN offset (para que la malla nazca en 0,0,0)
            shape_copy = shape_data.copy()
            shape_copy['offset'] = {'x': 0, 'y': 0, 'z': 0}

            # 2. Crear la malla centrada
            if shape_type == 'box':
                mesh = create_mesh_box_import(name + "_mesh", shape_copy, texture_width, texture_height)
            else:
                mesh = create_mesh_quad_import(name + "_mesh", shape_copy, texture_width, texture_height)
            
            mesh_obj = bpy.data.objects.new(name + "_shape", mesh)
            collection.objects.link(mesh_obj)

            # 3. Calcular dónde debe ir el Wrapper
            # Prioridad A: Offset explícito en JSON
            raw_offset = shape_data.get("offset", {'x': 0, 'y': 0, 'z': 0})
            target_pos = hytale_to_blender_pos(raw_offset)
            
            # Prioridad B: Si el offset es 0, verificar si la geometría tiene desplazamiento interno (from/to)
            # Esto corrige el caso donde 'offset' es 0 pero la caja está definida lejos del centro.
            if target_pos.length_squared < 0.0001:
                # Creamos una malla temporal con los datos originales para ver dónde cae
                temp_mesh = None
                if shape_type == 'box':
                    temp_mesh = create_mesh_box_import("Temp", shape_data, texture_width, texture_height)
                else:
                    temp_mesh = create_mesh_quad_import("Temp", shape_data, texture_width, texture_height)
                
                # Calculamos su centro
                center_vec = mathutils.Vector((0,0,0))
                if temp_mesh.vertices:
                    center_vec = sum((v.co for v in temp_mesh.vertices), mathutils.Vector()) / len(temp_mesh.vertices)
                
                # Si está lejos del centro, usamos esa posición como offset del Wrapper
                if center_vec.length > 0.01:
                    target_pos = center_vec
                
                # Limpiamos
                bpy.data.meshes.remove(temp_mesh)

            # 4. Crear el Wrapper (Geo) en la posición calculada
            geo_wrapper = bpy.data.objects.new(name + "_Geo", None)
            geo_wrapper.empty_display_type = 'PLAIN_AXES'
            geo_wrapper.empty_display_size = 0.2
            collection.objects.link(geo_wrapper)
            
            geo_wrapper.parent = node_empty
            geo_wrapper.location = target_pos # Aquí aplicamos la separación Padre <-> Geo
            geo_wrapper.rotation_mode = 'QUATERNION'
            geo_wrapper.rotation_quaternion = (1, 0, 0, 0)
            
            # 5. Malla dentro del Wrapper (en 0,0,0)
            mesh_obj.parent = geo_wrapper
            
        else:
            # Caso Normal (Sin hijos): Todo directo
            if shape_type == 'box':
                mesh = create_mesh_box_import(name + "_mesh", shape_data, texture_width, texture_height)
            else:
                mesh = create_mesh_quad_import(name + "_mesh", shape_data, texture_width, texture_height)
                
            mesh_obj = bpy.data.objects.new(name + "_shape", mesh)
            collection.objects.link(mesh_obj)
            mesh_obj.parent = node_empty
            
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
