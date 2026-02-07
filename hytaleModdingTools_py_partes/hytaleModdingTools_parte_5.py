# PARTE 5/5 - hytaleModdingTools.py
# CAMBIOS RECIENTES

            
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

class PT_HytalePanel(bpy.types.Panel):
    bl_label = "Hytale Tools v0.39"
    bl_idname = "VIEW3D_PT_hytale_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hytale'

    def draw(self, context):
        layout = self.layout
        props = context.scene.hytale_props
        
                
        # 0. DIAGNÓSTICO (Restaurado)
        draw_validator_ui(self, context, layout)
        
        #1. IMPORTACIÓN (Siempre visible)
        box = layout.box()
        box.label(text="Importar (Blockymodel):", icon='IMPORT')
        row = box.row()
        box.operator("hytale.import_model", icon='FILE_FOLDER', text="Cargar Modelo")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Utilidades & Referencias:", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.prop(props, "selected_reference", text="")
        row.operator("hytale.load_reference", icon='IMPORT', text="Cargar")
        
        layout.separator()
        
        # 2. CONFIGURACIÓN GENERAL (Setup)
        box_main = layout.box()
        box_main.label(text="Configuración de Escena", icon='PREFERENCES')
        box_main.separator()
        
        # SELECCIÓN DE COLECCIÓN (El interruptor principal)
        box_main.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
        has_collection = props.target_collection is not None
        if not has_collection:
            box_main.label(text="¡Selecciona colección para editar!", icon='INFO')
        row = box_main.row(align=True)
        box_main.prop(props, "setup_pixel_grid", text="Modo Pixel Perfect")
        if props.setup_pixel_grid:
            col_main = box_main.column()
            col_main.prop(props, "show_subdivisions", icon='GRID')

        box_main.separator()
        
        layout.separator()

        # 3. MATERIAL Y TEXTURA (El nuevo núcleo)
        box_mat = layout.box()
        box_mat.label(text="Material y Textura", icon='MATERIAL')
        box_mat.enabled = has_collection # Bloqueo visual si no hay colección
        
        col = box_mat.column(align=True)
        col.template_ID(props, "target_material", new="material.new")
        
        if props.target_material:
            col.separator()
            row = col.row(align=True)
            # template_ID para Textura (Nueva/Abrir/Seleccionar)
            row.template_ID(props, "target_image", new="image.new", open="image.open")
            
            # Botón de re-detección manual
            row.operator("hytale.detect_texture", icon='EYEDROPPER', text="")
            
            if props.target_image:
                row = col.row()
                row.alignment = 'CENTER'
                row.label(text=f"{props.target_image.size[0]} x {props.target_image.size[1]} px", icon='CHECKMARK')
        else:
            col.label(text="Selecciona Material Unificado", icon='ERROR')

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

        # 6. EXPORTACIÓN
        box_exp = layout.box()
        box_exp.label(text="Exportación", icon='EXPORT')
        box_exp.enabled = has_collection and (props.target_material is not None)
        
        col_exp = box_exp.column()
        col_exp.prop(props, "file_path", text="") # Restaurado path manual
        
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
