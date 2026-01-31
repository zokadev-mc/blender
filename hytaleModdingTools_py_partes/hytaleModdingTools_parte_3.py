# PARTE 3/3 - hytaleModdingTools.py
# CAMBIOS RECIENTES

def update_target_texture(self, context):
    """
    Callback: Cuando se selecciona una imagen en el panel,
    esta función la aplica automáticamente al material de los objetos.
    """
    target_img = self.target_image
    collection = self.target_collection
    
    # Validaciones básicas
    if not target_img: return
    if not collection: return # Si no hay colección seleccionada, no hacemos nada
        
    collection = bpy.data.collections[col_name]
    
    for obj in collection.objects:
        if obj.type == 'MESH':
            # 1. Obtener o crear material
            if not obj.data.materials:
                mat = bpy.data.materials.new(name=f"Hytale_{collection.name}_Mat")
                obj.data.materials.append(mat)
            else:
                mat = obj.data.materials[0]
            
            # 2. Activar nodos
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # 3. Buscar el nodo Principled BSDF
            bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            
            # Si el material está vacío o roto, lo reconstruimos
            if not bsdf:
                nodes.clear()
                bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                bsdf.location = (0, 0)
                out = nodes.new('ShaderNodeOutputMaterial')
                out.location = (300, 0)
                links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
            
            # 4. Configurar el nodo de Textura
            tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
            if not tex_node:
                tex_node = nodes.new('ShaderNodeTexImage')
                tex_node.location = (-300, 200)
            
            # Asignar la imagen seleccionada
            tex_node.image = target_img
            tex_node.interpolation = 'Closest' # Importante para Pixel Art/Minecraft style
            
            # 5. Conectar al Base Color y Alpha
            if 'Base Color' in bsdf.inputs:
                links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
            
            if 'Alpha' in bsdf.inputs:
                links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
                # Activar transparencia en el material para viewport
                mat.blend_method = 'CLIP'
                mat.shadow_method = 'CLIP'

# --- UI Y PANEL ---

class HytaleProperties(bpy.types.PropertyGroup):
    target_collection: bpy.props.PointerProperty(
        name="Colección",
        type=bpy.types.Collection,
        description="Selecciona la colección del modelo"
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
        col.prop(props, "target_collection", icon='OUTLINER_COLLECTION')
        
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
