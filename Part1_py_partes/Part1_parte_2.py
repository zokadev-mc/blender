# PARTE 2 DE 2 DEL ARCHIVO: Part1.py
# CONTINUACIÓN AUTOMÁTICA. EL CONTEXTO ANTERIOR ES NECESARIO.

def process_and_decompose_collection(source_col, temp_col):
    processed_roots = []
    old_to_new = {}
    
    for obj in source_col.objects:
        new_obj = obj.copy()
        new_obj.data = obj.data.copy() if obj.data else None
        temp_col.objects.link(new_obj)
        old_to_new[obj] = new_obj
        
    for old_obj, new_obj in old_to_new.items():
        if old_obj.parent and old_obj.parent in old_to_new:
            new_obj.parent = old_to_new[old_obj.parent]
        else:
            processed_roots.append(new_obj)

    # --- CAMBIO AÑADIDO: AISLAMIENTO INTELIGENTE DE HERMANOS ---
    # Detectar padres que tienen múltiples hijos Mesh y crear wrappers "GRP_"
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
    # ---------------------------------------------------------------------

    final_objects_to_check = list(old_to_new.values())
    bpy.ops.object.select_all(action='DESELECT')
    
    for obj in final_objects_to_check:
        if obj.type == 'MESH':
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            if len(obj.data.vertices) > 0:
                bpy.ops.mesh.separate(type='LOOSE')
            
            separated_parts = bpy.context.selected_objects
            
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
    x = h_pos.get("x", 0) / FIXED_GLOBAL_SCALE
    y = -h_pos.get("z", 0) / FIXED_GLOBAL_SCALE
    z = h_pos.get("y", 0) / FIXED_GLOBAL_SCALE
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

def create_mesh_box_import(name, shape_data, texture_width, texture_height):
    settings = shape_data.get("settings", {})
    size = settings.get("size", {})
    hx, hy, hz = size.get("x", 0), size.get("y", 0), size.get("z", 0)
    dx, dy, dz = hx/32.0, hz/32.0, hy/32.0
    
    bm = bmesh.new()
    v = [bm.verts.new((-dx, -dy, -dz)), bm.verts.new((dx, -dy, -dz)),
         bm.verts.new((dx, dy, -dz)), bm.verts.new((-dx, dy, -dz)),
         bm.verts.new((-dx, -dy, dz)), bm.verts.new((dx, -dy, dz)),
         bm.verts.new((dx, dy, dz)), bm.verts.new((-dx, dy, dz))]
    
    face_map = {
        "top":    (v[4], v[5], v[6], v[7]), "bottom": (v[0], v[1], v[2], v[3]),
        "front":  (v[0], v[1], v[5], v[4]), "back":   (v[2], v[3], v[7], v[6]),
        "left":   (v[3], v[0], v[4], v[7]), "right":  (v[1], v[2], v[6], v[5])
    }

    tex_layout = shape_data.get("textureLayout", {})
    for f_name, f_verts in face_map.items():
        if f_name in tex_layout:
            try:
                f = bm.faces.new(f_verts)
                if f_name in ['top', 'bottom']: fw, fh = hx, hz
                elif f_name in ['front', 'back']: fw, fh = hx, hy
                else: fw, fh = hz, hy
                apply_uvs_smart(f, bm, tex_layout[f_name], texture_width, texture_height, fw, fh)
            except: pass

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj_off = hytale_to_blender_pos(shape_data.get("offset", {}))
    for vert in mesh.vertices: vert.co += obj_off
    return mesh
