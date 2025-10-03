bl_info = {
    "name": "Aurora Borealis Generator",
    "author": "Gemini & C.L.",
    "version": (2, 3),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Create > Aurora Generator",
    "description": "Creates and updates a simple two-colored aurora from a Bezier curve or a drawn annotation.",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from bpy.props import (
    PointerProperty,
    FloatProperty,
    IntProperty,
    FloatVectorProperty,
    BoolProperty,
)
from bpy.types import PropertyGroup

# --- Properties ---
class AuroraGeneratorProperties(PropertyGroup):
    aurora_height: FloatProperty(
        name="Height",
        description="The vertical height of the aurora curtain",
        default=5.0,
        min=0.1
    )
    
    subdivisions: IntProperty(
        name="Resolution",
        description="Number of subdivisions along the curve. Higher is smoother",
        default=128,
        min=2,
        max=1024
    )
    
    color1: FloatVectorProperty(
        name="Bottom Color",
        subtype='COLOR',
        default=(0.1, 1.0, 0.7, 1.0), # Default bright green/cyan
        min=0.0,
        max=1.0,
        size=4
    )
    
    color2: FloatVectorProperty(
        name="Top Color",
        subtype='COLOR',
        default=(0.3, 0.2, 0.8, 1.0), # Default soft purple
        min=0.0,
        max=1.0,
        size=4
    )
    
    emission_strength: FloatProperty(
        name="Emission Strength",
        description="How bright the aurora glows",
        default=25.0,
        min=0.0
    )
    
    noise_scale: FloatProperty(
        name="Wispy Scale",
        description="Scale of the wispy noise pattern",
        default=1.5,
        min=0.1
    )
    
    noise_distortion: FloatProperty(
        name="Wispy Distortion",
        description="Distortion of the wispy noise pattern",
        default=0.5,
        min=0.0
    )

    animate: BoolProperty(
        name="Animate",
        description="Automatically add a simple animation driver",
        default=True
    )


# --- Draw Callback for Modal Operator ---
def draw_callback_px(self, context):
    if not self.points:
        return

    shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
    # Draw lines
    if len(self.points) > 1:
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": self.points})
        shader.bind()
        shader.uniform_float("color", (0.8, 0.8, 0.8, 1.0))
        batch.draw(shader)
    # Draw points
    batch = batch_for_shader(shader, 'POINTS', {"pos": self.points})
    shader.bind()
    shader.uniform_float("color", (0.2, 0.5, 1.0, 1.0))
    gpu.state.point_size_set(5)
    batch.draw(shader)

# --- Modal Operator to draw a curve by clicking ---
class CURVE_OT_DrawPath(bpy.types.Operator):
    """Draw a new Bezier curve in the 3D view by clicking"""
    bl_idname = "aurora.draw_path" # FIXED: More unique ID to prevent conflicts
    bl_label = "Draw Custom Path"
    bl_options = {'REGISTER', 'UNDO'}

    # REMOVED __init__ as it's better practice to initialize in invoke() for modal operators

    def modal(self, context, event):
        context.area.tag_redraw()

        if event.type in {'RIGHTMOUSE', 'RET'}:
            self.finish(context)
            return {'FINISHED'}

        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Get 3D location from mouse click
            region = context.region
            rv3d = context.region_data
            coord = event.mouse_region_x, event.mouse_region_y
            origin = region_2d_to_origin_3d(region, rv3d, coord)
            vec = region_2d_to_vector_3d(region, rv3d, coord)
            
            # Intersect with the Z=0 plane
            location = None
            if vec.z != 0:
                t = -origin.z / vec.z
                if t > 0:
                    location = origin + t * vec

            if location:
                self.points.append(location)
                self.update_curve(context)
            
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def update_curve(self, context):
        if not self.curve_ob:
            curve_data = bpy.data.curves.new('AuroraPath', type='CURVE')
            curve_data.dimensions = '3D'
            spline = curve_data.splines.new('BEZIER')
            self.curve_ob = bpy.data.objects.new('AuroraCurve', curve_data)
            context.collection.objects.link(self.curve_ob)
        
        spline = self.curve_ob.data.splines[0]
        num_points = len(self.points)
        
        if len(spline.bezier_points) < num_points:
             spline.bezier_points.add(num_points - len(spline.bezier_points))
        
        for i, point_co in enumerate(self.points):
            spline.bezier_points[i].co = point_co
            spline.bezier_points[i].handle_left_type = 'AUTO'
            spline.bezier_points[i].handle_right_type = 'AUTO'

    def finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        if self.curve_ob:
            bpy.ops.object.select_all(action='DESELECT')
            self.curve_ob.select_set(True)
            context.view_layer.objects.active = self.curve_ob
        context.window.cursor_set('DEFAULT')
        self.report({'INFO'}, "Path created.")

    def cancel(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        if self.curve_ob:
            bpy.data.objects.remove(self.curve_ob, do_unlink=True)
        context.window.cursor_set('DEFAULT')
        self.report({'INFO'}, "Path drawing cancelled.")

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            # FIXED: Initialize properties here instead of __init__
            self.points = []
            self.curve_ob = None
            self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, (self, context), 'WINDOW', 'POST_VIEW')
            context.window_manager.modal_handler_add(self)
            context.window.cursor_set('CROSSHAIR')
            self.report({'INFO'}, "Click to add points. Enter/Right-click to finish. Esc to cancel.")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a 3D View.")
            return {'CANCELLED'}

# --- Operator to Create Aurora ---
class AURORA_OT_Create(bpy.types.Operator):
    """Creates or updates an aurora mesh and material from the selected curve"""
    bl_idname = "object.create_aurora"
    bl_label = "Create / Update Aurora"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'CURVE'

    def execute(self, context):
        props = context.scene.aurora_props
        curve_object = context.active_object

        # --- Pre-Creation Cleanup ---
        if "aurora_object_name" in curve_object:
            old_aurora_name = curve_object["aurora_object_name"]
            old_aurora = bpy.data.objects.get(old_aurora_name)
            if old_aurora:
                old_mesh = old_aurora.data
                bpy.data.objects.remove(old_aurora, do_unlink=True)
                if old_mesh and old_mesh.users == 0:
                    bpy.data.meshes.remove(old_mesh)

        if "aurora_texture_name" in curve_object:
            old_tex_name = curve_object["aurora_texture_name"]
            old_tex = bpy.data.textures.get(old_tex_name)
            if old_tex and old_tex.users == 0:
                bpy.data.textures.remove(old_tex)
        
        # --- 1. Create the base mesh ---
        bpy.ops.mesh.primitive_plane_add(enter_editmode=True)
        aurora_object = context.active_object
        aurora_object.name = "Aurora"
        
        bpy.ops.transform.resize(value=(20, 1, 1))
        bpy.ops.transform.resize(value=(1, props.aurora_height / 2, 1))
        bpy.ops.mesh.subdivide(number_cuts=props.subdivisions, smoothness=0)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        aurora_object.rotation_euler[0] = 1.5708
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

        # --- 2. Add Modifiers ---
        curve_mod = aurora_object.modifiers.new(name="FollowCurve", type='CURVE')
        curve_mod.object = curve_object
        
        disp_mod = aurora_object.modifiers.new(name="Displacement", type='DISPLACE')
        disp_texture = bpy.data.textures.new('AuroraDisplaceTexture', type='CLOUDS')
        disp_texture.noise_scale = 0.5
        disp_mod.texture = disp_texture
        disp_mod.strength = 0.7
        disp_mod.direction = 'Z'
        
        # --- 3. Create or Update the Aurora Material ---
        mat = None
        if "aurora_material_name" in curve_object:
            old_mat_name = curve_object["aurora_material_name"]
            mat = bpy.data.materials.get(old_mat_name)

        if not mat:
            mat = bpy.data.materials.new(name="Aurora_Material")
            curve_object["aurora_material_name"] = mat.name

        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # Create all necessary nodes
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        mix_shader = nodes.new(type='ShaderNodeMixShader')
        emission = nodes.new(type='ShaderNodeEmission')
        transparent = nodes.new(type='ShaderNodeBsdfTransparent')
        color_ramp_main = nodes.new(type='ShaderNodeValToRGB')
        separate_xyz = nodes.new(type='ShaderNodeSeparateXYZ')
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        noise_tex = nodes.new(type='ShaderNodeTexNoise')
        mapping_anim = nodes.new(type='ShaderNodeMapping')
        mapping_stretch = nodes.new(type='ShaderNodeMapping')
        
        emission_falloff_ramp = nodes.new(type='ShaderNodeValToRGB')
        multiply_emission = nodes.new(type='ShaderNodeMath')
        multiply_emission.operation = 'MULTIPLY'
        
        vertical_fade_ramp = nodes.new(type='ShaderNodeValToRGB')
        combine_fade_and_noise = nodes.new(type='ShaderNodeMath')
        combine_fade_and_noise.operation = 'MAXIMUM'
        
        output_node.location = (600, 0)
        mix_shader.location = (400, 0)
        transparent.location = (200, -200)
        emission.location = (200, 100)
        multiply_emission.location = (0, 200)
        emission_falloff_ramp.location = (-200, 200)
        color_ramp_main.location = (-200, 100)
        separate_xyz.location = (-400, 100)
        tex_coord.location = (-600, 100)
        combine_fade_and_noise.location = (200, -50)
        vertical_fade_ramp.location = (0, 0)
        noise_tex.location = (0, -200)
        mapping_stretch.location = (-200, -200)
        mapping_anim.location = (-400, -200)

        # --- Configure node properties ---
        color_ramp_main.color_ramp.elements[0].color = props.color1
        color_ramp_main.color_ramp.elements[1].color = props.color2

        emission_falloff_ramp.color_ramp.elements[0].position = 0.0
        emission_falloff_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
        emission_falloff_ramp.color_ramp.elements[1].position = 1.0
        emission_falloff_ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
        multiply_emission.inputs[1].default_value = props.emission_strength

        vertical_fade_ramp.color_ramp.elements[0].position = 0.0
        vertical_fade_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
        vertical_fade_ramp.color_ramp.elements.new(0.3)
        vertical_fade_ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
        vertical_fade_ramp.color_ramp.elements[2].position = 1.0
        vertical_fade_ramp.color_ramp.elements[2].color = (0, 0, 0, 1)

        mapping_stretch.inputs['Scale'].default_value[0] = 0.2
        mapping_stretch.inputs['Scale'].default_value[1] = 10.0
        noise_tex.inputs['Scale'].default_value = props.noise_scale
        noise_tex.inputs['Detail'].default_value = 5.0
        noise_tex.inputs['Roughness'].default_value = 0.6
        noise_tex.inputs['Distortion'].default_value = props.noise_distortion

        # --- 4. Link Nodes Together ---
        links.new(tex_coord.outputs['Generated'], separate_xyz.inputs['Vector'])
        links.new(separate_xyz.outputs['Y'], color_ramp_main.inputs['Fac'])
        links.new(color_ramp_main.outputs['Color'], emission.inputs['Color'])
        links.new(separate_xyz.outputs['Y'], emission_falloff_ramp.inputs['Fac'])
        links.new(emission_falloff_ramp.outputs['Color'], multiply_emission.inputs[0])
        links.new(multiply_emission.outputs['Value'], emission.inputs['Strength'])
        links.new(tex_coord.outputs['Generated'], mapping_anim.inputs['Vector'])
        links.new(mapping_anim.outputs['Vector'], mapping_stretch.inputs['Vector'])
        links.new(mapping_stretch.outputs['Vector'], noise_tex.inputs['Vector'])
        links.new(separate_xyz.outputs['Y'], vertical_fade_ramp.inputs['Fac'])
        links.new(vertical_fade_ramp.outputs['Color'], combine_fade_and_noise.inputs[0])
        links.new(noise_tex.outputs['Fac'], combine_fade_and_noise.inputs[1])
        links.new(combine_fade_and_noise.outputs['Value'], mix_shader.inputs['Fac'])
        links.new(emission.outputs['Emission'], mix_shader.inputs[1])
        links.new(transparent.outputs['BSDF'], mix_shader.inputs[2])
        links.new(mix_shader.outputs['Shader'], output_node.inputs['Surface'])
        
        # --- 5. Add animation driver ---
        if props.animate:
            mapping_anim.inputs['Location'].keyframe_insert(data_path='default_value', frame=1)
            mapping_anim.inputs['Location'].default_value[1] = 5.0
            mapping_anim.inputs['Location'].keyframe_insert(data_path='default_value', frame=250)
            if mat.node_tree.animation_data and mat.node_tree.animation_data.action:
                for fcurve in mat.node_tree.animation_data.action.fcurves:
                     if fcurve.data_path.endswith("['Location']"):
                        for k in fcurve.keyframe_points:
                            k.interpolation = 'LINEAR'
                        mod = fcurve.modifiers.new('CYCLES')

        # --- 6. Assign material and finalize ---
        aurora_object.data.materials.append(mat)
        curve_object["aurora_object_name"] = aurora_object.name
        curve_object["aurora_texture_name"] = disp_texture.name
        
        curve_object.select_set(False)
        aurora_object.select_set(True)
        context.view_layer.objects.active = aurora_object

        self.report({'INFO'}, "Aurora created/updated successfully!")
        return {'FINISHED'}

# --- Panel ---
class VIEW3D_PT_AuroraPanel(bpy.types.Panel):
    bl_label = "Aurora Generator"
    bl_idname = "VIEW3D_PT_aurora_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Create'

    def draw(self, context):
        layout = self.layout
        props = context.scene.aurora_props

        # --- Draw Path section ---
        box = layout.box()
        box.label(text="Draw Path", icon='CURVE_PATH')
        col = box.column()
        col.operator(CURVE_OT_DrawPath.bl_idname, icon='ADD')
        col.label(text="Click to start drawing a path in the scene.")

        layout.separator()

        # --- Existing Aurora settings ---
        box = layout.box()
        box.label(text="Generate Aurora", icon='SHADERFX')
        
        if context.active_object and context.active_object.type == 'CURVE':
            col = box.column(align=True)
            col.prop(props, "aurora_height")
            col.prop(props, "subdivisions")
            
            sub_box = box.box()
            sub_box.label(text="Colors & Glow")
            sub_box.prop(props, "color1")
            sub_box.prop(props, "color2")
            sub_box.prop(props, "emission_strength")
            
            sub_box = box.box()
            sub_box.label(text="Pattern")
            sub_box.prop(props, "noise_scale")
            sub_box.prop(props, "noise_distortion")
            
            box.prop(props, "animate")
            box.separator()

            box.operator(AURORA_OT_Create.bl_idname, icon='SHADERFX')
        else:
            box.label(text="Select a Curve object to generate.", icon='INFO')


# --- Registration ---
classes = (
    AuroraGeneratorProperties,
    CURVE_OT_DrawPath,
    AURORA_OT_Create,
    VIEW3D_PT_AuroraPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aurora_props = PointerProperty(type=AuroraGeneratorProperties)

def unregister():
    del bpy.types.Scene.aurora_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

