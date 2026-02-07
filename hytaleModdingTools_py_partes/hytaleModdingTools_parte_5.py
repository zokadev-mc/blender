# PARTE 5/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES

            
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
        
# --- MEMORIA ESTRICTA ---
# Guardamos el estado del nodo por material.
# Solo actualizamos el menú si el NODO cambia respecto a esta memoria.
_node_state_cache = {}
_last_viewed_mat = None

def sync_menu_from_node(props, image):
    try:
        if props.target_image != image:
            props.target_image = image
    except: pass
    return None

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.40"
    bl_idname = "VIEW3D_PT_hytale_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hytale'

    def draw(self, context):
        global _last_viewed_mat
        layout = self.layout
        props = context.scene.hytale_props
        
        # 1. ANALIZAR ESTADO DE CONEXIÓN REAL
        current_node_image = None
        is_node_connected = False
        mat = props.target_material

        if mat and mat.use_nodes:
            tree = mat.node_tree
            bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            # La clave es 'is_linked': si no hay cable, para el menú no hay textura
            if bsdf and bsdf.inputs['Base Color'].is_linked:
                link_node = bsdf.inputs['Base Color'].links[0].from_node
                if link_node.type == 'TEX_IMAGE':
                    is_node_connected = True
                    current_node_image = link_node.image

        # 2. MONITOR DE CABLES (Tiempo Real)
        if mat:
            mat_name = mat.name
            cached_image = _node_state_cache.get(mat_name)
            
            if mat != _last_viewed_mat:
                _node_state_cache[mat_name] = current_node_image
                _last_viewed_mat = mat
            
            elif current_node_image != cached_image:
                # Si el cable se cortó o cambió, sincronizamos el menú
                bpy.app.timers.register(lambda: sync_menu_from_node(props, current_node_image), first_interval=0.01)
                _node_state_cache[mat_name] = current_node_image

        # DIAGNÓSTICO
        try: draw_validator_ui(self, context, layout)
        except: pass
        
        # IMPORTAR
        box = layout.box()
        box.label(text="Importar (Blockymodel):", icon='IMPORT')
        box.operator("hytale.import_model", icon='FILE_FOLDER', text="Cargar Modelo")
        layout.separator()
        
        # UTILIDADES
        box = layout.box()
        box.label(text="Utilidades & Referencias:", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.prop(props, "selected_reference", text="")
        row.operator("hytale.load_reference", icon='IMPORT', text="Cargar")
        layout.separator()
        
        # ESCENA
        box_main = layout.box()
        box_main.label(text="Configuración de Escena", icon='PREFERENCES')
        box_main.separator()
        box_main.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
        has_collection = props.target_collection is not None
        if not has_collection:
            box_main.label(text="¡Selecciona colección para editar!", icon='INFO')
        
        row = box_main.row(align=True)
        box_main.prop(props, "setup_pixel_grid", text="Modo Pixel Perfect")
        if props.setup_pixel_grid:
            col_main = box_main.column()
            col_main.prop(props, "show_subdivisions", icon='GRID')

        layout.separator()

        # --- MATERIAL Y TEXTURA ---
        box_mat = layout.box()
        box_mat.label(text="Material y Textura", icon='MATERIAL')
        box_mat.enabled = has_collection
        
        col = box_mat.column(align=True)
        col.template_ID(props, "target_material", new="material.new")
        
        if props.target_material:
            col.separator()
            
            # Selector Principal
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
                row.label(text="Asigna una textura", icon='INFO')
        else:
            col.label(text="Selecciona Material Unificado", icon='ERROR')

        layout.separator()

        # UV Y EXPORTACIÓN
        box = layout.box()
        row_uv = box.row()
        row_uv.label(text="Herramientas UV:", icon='UV_DATA')
        
        # Activamos herramientas si hay textura en el NODO (independiente del menú)
        is_uv_enabled = has_collection and is_node_connected and current_node_image
        box.enabled = bool(is_uv_enabled)
        
        if not is_uv_enabled:
             if not has_collection:
                 box.label(text="(Requiere Colección)", icon='SMALL_TRIANGLE_RIGHT_DOWN')
             elif not is_node_connected:
                 box.label(text="(Falta Textura)", icon='SMALL_TRIANGLE_RIGHT_DOWN')

        box.prop(props, "new_unwrap")
        box.prop(props, "auto_stack", text="Auto Stack Similar UV Islands")
        box.operator("hytale.pixel_perfect_pack", icon='UV_SYNC_SELECT', text="Pixel Perfect Pack")
        
        is_active = context.scene.hytale_uv_active
        box.operator("hytale.toggle_uv_measures", icon="DRIVER_DISTANCE", text="Mostrar Medidas En UV's", depress=is_active)
        
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
