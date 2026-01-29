"""
Universal 3D Model Thumbnail Renderer for Luma Tools.

Renders thumbnails for GLB, FBX, OBJ, USD, and other 3D formats using Open3D.
Supports both mesh rendering and skeleton visualization for mocap files.

This script runs as a separate process to avoid OpenGL context conflicts with Qt.

Usage:
    python thumbnail_renderer.py <input_model_path> <output_png_path> [size]
"""

import sys
import os
import logging

logger = logging.getLogger(__name__)


def _ensure_output_dir(path):
    """Ensure the output directory exists."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)


def render_thumbnail(model_path: str, output_path: str, size: int = 150) -> bool:
    """
    Render a 3D model file to a PNG thumbnail using Open3D.

    Args:
        model_path: Path to the 3D model file (GLB, FBX, OBJ, USD, etc.)
        output_path: Path to save the PNG thumbnail
        size: Size of the square thumbnail (in pixels)

    Returns:
        True if successful, False otherwise
    """
    try:
        import open3d as o3d
        import numpy as np

        # Load the model with Open3D
        mesh = o3d.io.read_triangle_mesh(model_path, enable_post_processing=True)

        if mesh.is_empty():
            logger.error(f"Failed to load mesh or mesh is empty: {model_path}")
            return False

        # Compute vertex normals if not present (required for proper lighting)
        if not mesh.has_vertex_normals():
            mesh.compute_vertex_normals()

        # If mesh doesn't have vertex colors, apply a neutral gray
        if not mesh.has_vertex_colors():
            mesh.paint_uniform_color([0.7, 0.7, 0.7])

        # Get bounding box for camera positioning with robust handling
        bbox = mesh.get_axis_aligned_bounding_box()
        center = bbox.get_center()
        extent = bbox.get_extent()

        # Robust bounding box validation
        # Check for invalid values (NaN, Inf, or degenerate bounds)
        if (not np.isfinite(center).all() or not np.isfinite(extent).all() or
            np.allclose(extent, 0)):
            # Fallback: compute bounds directly from vertices
            vertices = np.asarray(mesh.vertices)
            if len(vertices) > 0:
                # Filter out non-finite vertices
                valid_mask = np.isfinite(vertices).all(axis=1)
                valid_vertices = vertices[valid_mask]
                if len(valid_vertices) > 0:
                    bounds_min = np.min(valid_vertices, axis=0)
                    bounds_max = np.max(valid_vertices, axis=0)
                    center = (bounds_min + bounds_max) / 2
                    extent = bounds_max - bounds_min
                else:
                    center = np.array([0.0, 0.0, 0.0])
                    extent = np.array([1.0, 1.0, 1.0])
            else:
                center = np.array([0.0, 0.0, 0.0])
                extent = np.array([1.0, 1.0, 1.0])

        # Ensure each extent dimension has a minimum value to avoid flat views
        extent = np.maximum(extent, 0.001)
        max_extent = max(extent)

        if max_extent < 0.001:
            max_extent = 1.0

        # Create visualizer with hidden window
        vis = o3d.visualization.Visualizer()
        vis.create_window(width=size, height=size, visible=False)

        # Add mesh
        vis.add_geometry(mesh)

        # Get render options and set background color
        render_opt = vis.get_render_option()
        render_opt.background_color = np.array([0.165, 0.188, 0.25])  # Dark theme
        render_opt.light_on = True
        # Disable grid and axis lines for clean thumbnails
        render_opt.show_coordinate_frame = False

        # Calculate camera position for 3/4 view
        distance = max_extent * 2.0
        pitch = np.radians(25)
        yaw = np.radians(45)

        cam_x = center[0] + distance * np.cos(pitch) * np.sin(yaw)
        cam_y = center[1] - distance * np.sin(pitch)
        cam_z = center[2] + distance * np.cos(pitch) * np.cos(yaw)

        eye = np.array([cam_x, cam_y, cam_z])
        up = np.array([0, 1, 0])
        front = center - eye
        front = front / np.linalg.norm(front)

        # Set camera view
        ctr = vis.get_view_control()
        ctr.set_lookat(center)
        ctr.set_front(front)
        ctr.set_up(up)
        ctr.set_zoom(0.7)

        # Render and capture
        vis.poll_events()
        vis.update_renderer()

        # Ensure output directory exists
        _ensure_output_dir(output_path)

        # Capture to file
        vis.capture_screen_image(output_path, do_render=True)

        vis.destroy_window()

        return True

    except Exception as e:
        logger.error(f"Rendering failed: {e}", exc_info=True)
        return False


def render_skeleton_thumbnail(model_path: str, output_path: str, size: int = 150) -> bool:
    """
    Render a skeleton/mocap file to a PNG thumbnail.

    Args:
        model_path: Path to the model file with skeleton data
        output_path: Path to save the PNG thumbnail
        size: Size of the square thumbnail (in pixels)

    Returns:
        True if successful, False otherwise
    """
    try:
        import open3d as o3d
        import numpy as np
        from geo.loader import load_model

        # Load with our model loader to get skeleton data
        model_data = load_model(model_path)

        if not model_data.has_skeleton:
            logger.error("No skeleton data found")
            return False

        skeleton = model_data.skeleton

        # Extract bone positions
        bone_positions = []
        for bone in skeleton.bones:
            transform = bone.local_transform
            pos = np.array([transform[0, 3], transform[1, 3], transform[2, 3]])
            bone_positions.append(pos)

        bone_positions = np.array(bone_positions)

        if len(bone_positions) == 0:
            return False

        # Calculate bounds with robust handling
        # Filter out any non-finite bone positions
        valid_mask = np.isfinite(bone_positions).all(axis=1)
        valid_positions = bone_positions[valid_mask]

        if len(valid_positions) == 0:
            # Fallback if no valid positions
            center = np.array([0.0, 0.0, 0.0])
            extent = np.array([1.0, 1.0, 1.0])
        else:
            bounds_min = np.min(valid_positions, axis=0)
            bounds_max = np.max(valid_positions, axis=0)
            center = (bounds_min + bounds_max) / 2
            extent = bounds_max - bounds_min

            # Handle degenerate bounds (all bones at same position or nearly so)
            if not np.isfinite(center).all() or not np.isfinite(extent).all():
                center = np.array([0.0, 0.0, 0.0])
                extent = np.array([1.0, 1.0, 1.0])

        # Ensure minimum extent in each dimension
        extent = np.maximum(extent, 0.001)
        max_extent = max(max(extent), 0.1)

        # Create line set for bones
        line_set = None
        lines = []
        for i, bone in enumerate(skeleton.bones):
            if bone.parent_index >= 0:
                lines.append([bone.parent_index, i])

        if lines:
            line_set = o3d.geometry.LineSet()
            line_set.points = o3d.utility.Vector3dVector(bone_positions)
            line_set.lines = o3d.utility.Vector2iVector(lines)
            line_set.colors = o3d.utility.Vector3dVector([[0.9, 0.9, 0.9]] * len(lines))

        # Create spheres for joints
        geometries = []
        joint_radius = max_extent * 0.02

        for i, bone in enumerate(skeleton.bones):
            sphere = o3d.geometry.TriangleMesh.create_sphere(radius=joint_radius)
            sphere.translate(bone_positions[i])

            # Root joints are green, others are orange
            if bone.parent_index < 0:
                sphere.paint_uniform_color([0.4, 1.0, 0.6])
            else:
                sphere.paint_uniform_color([1.0, 0.6, 0.2])

            sphere.compute_vertex_normals()
            geometries.append(sphere)

        # Create visualizer with hidden window
        vis = o3d.visualization.Visualizer()
        vis.create_window(width=size, height=size, visible=False)

        # Add geometries
        for geom in geometries:
            vis.add_geometry(geom)

        if line_set:
            vis.add_geometry(line_set)

        # Get render options and set background color
        render_opt = vis.get_render_option()
        render_opt.background_color = np.array([0.165, 0.188, 0.25])
        render_opt.light_on = True
        render_opt.line_width = 3.0
        # Disable grid and axis lines for clean thumbnails
        render_opt.show_coordinate_frame = False

        # Camera setup
        distance = max_extent * 3.0
        pitch = np.radians(25)
        yaw = np.radians(45)

        cam_x = center[0] + distance * np.cos(pitch) * np.sin(yaw)
        cam_y = center[1] - distance * np.sin(pitch)
        cam_z = center[2] + distance * np.cos(pitch) * np.cos(yaw)

        eye = np.array([cam_x, cam_y, cam_z])
        front = center - eye
        front = front / np.linalg.norm(front)

        ctr = vis.get_view_control()
        ctr.set_lookat(center)
        ctr.set_front(front)
        ctr.set_up([0, 1, 0])
        ctr.set_zoom(0.5)

        # Render
        vis.poll_events()
        vis.update_renderer()

        _ensure_output_dir(output_path)
        vis.capture_screen_image(output_path, do_render=True)

        vis.destroy_window()

        return True

    except Exception as e:
        logger.error(f"Skeleton rendering failed: {e}", exc_info=True)
        return False


def render_placeholder_thumbnail(output_path: str, size: int = 150, label: str = "FBX") -> bool:
    """
    Render a placeholder thumbnail for files that can't be loaded.

    Args:
        output_path: Path to save the PNG thumbnail
        size: Size of the square thumbnail (in pixels)
        label: Label to display on the placeholder

    Returns:
        True if successful, False otherwise
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Create dark background
        img = Image.new('RGBA', (size, size), (42, 48, 64, 255))
        draw = ImageDraw.Draw(img)

        # Draw border
        border_color = (74, 158, 255, 180)
        draw.rectangle([2, 2, size-3, size-3], outline=border_color, width=2)

        # Draw 3D cube icon
        cx, cy = size // 2, size // 2 - 15
        cube_size = size // 4

        # Simple 3D cube lines
        points = [
            # Front face
            (cx - cube_size, cy - cube_size // 2),
            (cx + cube_size, cy - cube_size // 2),
            (cx + cube_size, cy + cube_size),
            (cx - cube_size, cy + cube_size),
            # Back face offset
            (cx - cube_size + cube_size // 2, cy - cube_size),
            (cx + cube_size + cube_size // 2, cy - cube_size),
            (cx + cube_size + cube_size // 2, cy + cube_size // 2),
        ]

        line_color = (120, 140, 180, 255)
        # Front face
        draw.line([points[0], points[1], points[2], points[3], points[0]], fill=line_color, width=2)
        # Top lines to back
        draw.line([points[0], points[4]], fill=line_color, width=2)
        draw.line([points[1], points[5]], fill=line_color, width=2)
        # Back top
        draw.line([points[4], points[5]], fill=line_color, width=2)
        # Right side to back
        draw.line([points[2], points[6]], fill=line_color, width=2)
        draw.line([points[5], points[6]], fill=line_color, width=2)

        # Draw label
        try:
            font = ImageFont.truetype("arial.ttf", size // 8)
        except Exception:
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text((cx - text_width // 2, cy + cube_size + 10), label, fill=(180, 180, 200, 255), font=font)

        # Ensure output directory exists
        _ensure_output_dir(output_path)

        # Save
        img.save(output_path, format='PNG')
        return True

    except Exception as e:
        logger.error(f"Placeholder rendering failed: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        logger.error("Usage: python thumbnail_renderer.py <input_model> <output_png> [size]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 150

    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    # Try regular mesh rendering first
    success = render_thumbnail(input_path, output_path, size)

    # If mesh rendering failed, try skeleton rendering (for mocap FBX files)
    if not success:
        logger.info("Mesh rendering failed, trying skeleton rendering...")
        success = render_skeleton_thumbnail(input_path, output_path, size)

    # If all rendering failed, generate a placeholder thumbnail
    if not success:
        ext = os.path.splitext(input_path)[1].upper().replace('.', '')
        logger.info(f"Skeleton rendering failed, generating placeholder for {ext}...")
        success = render_placeholder_thumbnail(output_path, size, label=ext or "3D")

    sys.exit(0 if success else 1)
