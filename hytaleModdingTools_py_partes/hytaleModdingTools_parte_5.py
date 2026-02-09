# PARTE 5/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES

                    
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
            
        # Buscar el primer nodo de imagen con una imagen asignada
        found_image = None
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                found_image = node.image
                break
        
        if found_image:
            props.target_image = found_image
            self.report({'INFO'}, f"Textura detectada: {found_image.name}")
        else:
            self.report({'WARNING'}, "No se encontró ninguna textura en el material")
            
        return {'FINISHED'}
        
# --- MEMORIA DEL MONITOR UI ---
_node_cache_state = {}
_ui_last_mat = None
_ui_last_obj_mat = None
_ui_last_collection = None

def sync_ui_task(props, img):
    try:
        if props.target_image != img:
            props.target_image = img
    except: pass
    return None

def sync_material_task(props, mat):
    try:
        if props.target_material != mat:
            props.target_material = mat
    except: pass
    return None

def get_collection_object(props):
    """Busca un objeto MESH válido en la colección para monitorear."""
    if props.target_collection:
        for obj in props.target_collection.objects:
            if obj.type == 'MESH':
                return obj
    return None

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.40"
    bl_idname = "VIEW3D_PT_hytale_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hytale'

    def draw(self, context):
        global _ui_last_mat, _ui_last_obj_mat, _ui_last_collection
        
        layout = self.layout
        props = context.scene.hytale_props
        
        # OBJETO MONITOR (Líder de la colección)
        target_obj = get_collection_object(props)
        
        # --- 1. MONITOR DE MATERIALES ---
        if target_obj:
            real_active_mat = target_obj.active_material
            
            # Detectar cambio de colección
            collection_changed = (props.target_collection != _ui_last_collection)
            if collection_changed:
                _ui_last_collection = props.target_collection
            
            # Sincronizar si el material real difiere del menú
            if real_active_mat != props.target_material:
                if collection_changed or real_active_mat != _ui_last_obj_mat:
                    bpy.app.timers.register(lambda: sync_material_task(props, real_active_mat), first_interval=0.01)
                    _ui_last_obj_mat = real_active_mat
            else:
                _ui_last_obj_mat = real_active_mat
        else:
            _ui_last_obj_mat = None
        # --------------------------------

        # 2. ESTADO REAL DE TEXTURA (NODOS)
        real_img = None
        connected = False
        mat = props.target_material

        if mat and mat.use_nodes:
            tree = mat.node_tree
            bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf and bsdf.inputs['Base Color'].is_linked:
                link_node = bsdf.inputs['Base Color'].links[0].from_node
                if link_node.type == 'TEX_IMAGE':
                    connected = True
                    real_img = link_node.image

        # 3. MONITOR DE CABLES
        if mat:
            mat_id = mat.name
            cached = _node_cache_state.get(mat_id, "NONE_SENTINEL")
            
            if mat != _ui_last_mat:
                _node_cache_state[mat_id] = real_img
                _ui_last_mat = mat
            elif real_img != cached:
                bpy.app.timers.register(lambda: sync_ui_task(props, real_img), first_interval=0.01)
                _node_cache_state[mat_id] = real_img

        # --- INTERFAZ ---
        try: draw_validator_ui(self, context, layout)
        except: pass
        
        # Importar
        box = layout.box()
        box.label(text="Importar (Blockymodel):", icon='IMPORT')
        box.operator("hytale.import_model", icon='FILE_FOLDER', text="Cargar Modelo")
        layout.separator()
        
        # Utilidades
        box = layout.box()
        box.label(text="Utilidades & Referencias:", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.prop(props, "selected_reference", text="")
        row.operator("hytale.load_reference", icon='IMPORT', text="Cargar")
        layout.separator()
        
        # Escena
        box_main = layout.box()
        box_main.label(text="Configuración de Escena", icon='PREFERENCES')
        box_main.separator()
        box_main.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
        has_collection = props.target_collection is not None
        if not has_collection:
            box_main.label(text="¡Selecciona colección para editar!", icon='INFO')
        elif not target_obj:
            box_main.label(text="Colección vacía (Sin MESH)", icon='ERROR')
        
        row = box_main.row(align=True)
        box_main.prop(props, "setup_pixel_grid", text="Modo Pixel Perfect")
        if props.setup_pixel_grid:
            col_main = box_main.column()
            col_main.prop(props, "show_subdivisions", icon='GRID')

        layout.separator()

        # Material
        box_mat = layout.box()
        box_mat.label(text="Material y Textura", icon='MATERIAL')
        box_mat.enabled = has_collection and (target_obj is not None)
        
        col = box_mat.column(align=True)
        col.template_ID(props, "target_material", new="material.new")
        
        if props.target_material:
            col.separator()
            row = col.row(align=True)
            row.template_ID(props, "target_image", new="image.new", open="image.open")
            row.operator("hytale.detect_texture", icon='EYEDROPPER', text="")

            if props.target_image:
                row = col.row()
                row.alignment = 'CENTER'
                row.label(text=f"{props.target_image.size[0]} x {props.target_image.size[1]} px", icon='CHECKMARK')
            else:
                row = col.row()
                row.alignment = 'CENTER'
                row.label(text="Sin textura (Desconectado)", icon='INFO')
        else:
            col.label(text="Sin Material Seleccionado", icon='ERROR')

        layout.separator()

        # UV / Export
        is_uv_enabled = has_collection and connected and target_obj
        
        box_uv = layout.box()
        box_uv.enabled = bool(is_uv_enabled)
        box_uv.label(text="Herramientas UV:", icon='UV_DATA')
        
        if not is_uv_enabled:
             # --- AQUI ESTABA EL ERROR: CAMBIADO A 'TRIA_RIGHT' ---
             if not has_collection:
                 box_uv.label(text="(Requiere Colección)", icon='TRIA_RIGHT')
             elif not connected:
                 box_uv.label(text="(Falta Textura)", icon='TRIA_RIGHT')
             # -----------------------------------------------------

        box_uv.prop(props, "new_unwrap")
        box_uv.prop(props, "auto_stack", text="Auto Stack Similar UV Islands")
        box_uv.operator("hytale.pixel_perfect_pack", icon='UV_SYNC_SELECT', text="Pixel Perfect Pack")
        
        is_active = context.scene.hytale_uv_active
        box_uv.operator("hytale.toggle_uv_measures", icon="DRIVER_DISTANCE", text="Mostrar Medidas En UV's", depress=is_active)
        
        layout.separator()

        box_exp = layout.box()
        box_exp.label(text="Exportación", icon='EXPORT')
        box_exp.enabled = bool(is_uv_enabled)
        col_exp = box_exp.column()
        col_exp.prop(props, "file_path", text="")
        row = col_exp.row()
        row.scale_y = 1.5
        row.operator("hytale.export_model", icon='CHECKMARK', text="EXPORTAR MODELO")

classes = (HytaleProperties, OPS_OT_SetupHytaleScene, OPS_OT_LoadReference, OPS_OT_ExportHytale, OPS_OT_ImportHytale, PT_HytalePanel, OPS_OT_DetectTexture, OPS_OT_PixelPerfectPack, OPS_OT_ToggleUVMeasures)

def register():
    bpy.types.Scene.hytale_uv_active = bpy.props.BoolProperty(default=False)
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.hytale_props = bpy.props.PointerProperty(type=HytaleProperties)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hytale_props
    del bpy.types.Scene.hytale_uv_active

if __name__ == "__main__": register()
