# PARTE 2 DE 2 DEL ARCHIVO: Part2.py
# CONTINUACIÓN AUTOMÁTICA. EL CONTEXTO ANTERIOR ES NECESARIO.

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
