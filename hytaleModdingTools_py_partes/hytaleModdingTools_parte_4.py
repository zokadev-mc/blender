# PARTE 4/4 - hytaleModdingTools.py
# CAMBIOS RECIENTES


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

            tex_w, tex_h = 64, 64
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

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.38"
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
        
        is_active = context.scene.hytale_uv_active
        box.operator("hytale.toggle_uv_measures", icon="DRIVER_DISTANCE", text="Mostrar Medidas En UV's", depress=is_active)
        
        layout.separator()
        
        # --- EXPORTACIÓN Y TEXTURAS ---
        box = layout.box()
        box.label(text="Configuración de Exportación:", icon='EXPORT')
        col = box.column(align=True)
        
        # 1. Elegir Colección
        col.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
        # 2. Elegir Material (Solo si hay colección)
        if props.target_collection:
            col.separator()
            col.label(text="Material Unificado:", icon='MATERIAL')
            col.prop(props, "target_material", text="")
            
        # 3. Elegir Textura (Solo si hay Material)
        if props.target_collection and props.target_material:
            col.separator()
            col.label(text="Configuración de Textura:", icon='TEXTURE')
            
            row = col.row(align=True)
            row.prop(props, "resolution_mode", expand=True)
            
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
                    box_inner.label(text="¡Selecciona una imagen!", icon='INFO')
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

classes = (HytaleProperties, OPS_OT_SetupHytaleScene, OPS_OT_LoadReference, OPS_OT_ExportHytale, OPS_OT_ImportHytale, PT_HytalePanel, OPS_OT_PixelPerfectPack, OPS_OT_ToggleUVMeasures)

def register():
    bpy.types.Scene.hytale_uv_active = bpy.props.BoolProperty(default=False)
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.hytale_props = bpy.props.PointerProperty(type=HytaleProperties)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hytale_props
    del bpy.types.Scene.hytale_uv_active

if __name__ == "__main__": register()
