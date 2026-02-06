# PARTE 2/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES

            
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
