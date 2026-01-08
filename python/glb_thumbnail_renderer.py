"""
Standalone GLB thumbnail renderer.

This script runs as a separate process to avoid OpenGL context conflicts with Qt.
It renders a GLB/GLTF file to a PNG thumbnail using trimesh and pyrender.

Usage:
    python glb_thumbnail_renderer.py <input_glb_path> <output_png_path> [size]
"""

import sys
import os
import math

# Set environment before importing pyrender
os.environ['PYOPENGL_PLATFORM'] = 'pyglet'


def render_thumbnail(glb_path: str, output_path: str, size: int = 150) -> bool:
    """
    Render a GLB file to a PNG thumbnail.

    Args:
        glb_path: Path to the GLB/GLTF file
        output_path: Path to save the PNG thumbnail
        size: Size of the square thumbnail

    Returns:
        True if successful, False otherwise
    """
    try:
        import numpy as np
        import trimesh
        import pyrender
        from PIL import Image

        # Load the model
        scene_or_mesh = trimesh.load(glb_path)

        # Create pyrender scene
        pr_scene = pyrender.Scene(
            bg_color=[0.16, 0.18, 0.22, 1.0],  # Dark background matching UI
            ambient_light=[0.3, 0.3, 0.3]
        )

        # Add meshes to scene
        if isinstance(scene_or_mesh, trimesh.Scene):
            for name, geometry in scene_or_mesh.geometry.items():
                if isinstance(geometry, trimesh.Trimesh):
                    mesh = pyrender.Mesh.from_trimesh(geometry)
                    if mesh:
                        try:
                            transform = scene_or_mesh.graph.get(name)[0]
                        except:
                            transform = np.eye(4)
                        pr_scene.add(mesh, pose=transform)
        elif isinstance(scene_or_mesh, trimesh.Trimesh):
            mesh = pyrender.Mesh.from_trimesh(scene_or_mesh)
            if mesh:
                pr_scene.add(mesh)
        else:
            print(f"Unsupported mesh type: {type(scene_or_mesh)}", file=sys.stderr)
            return False

        # Calculate bounds
        if isinstance(scene_or_mesh, trimesh.Scene):
            bounds = scene_or_mesh.bounds
        else:
            bounds = scene_or_mesh.bounds

        if bounds is None:
            print("Could not determine bounds", file=sys.stderr)
            return False

        center = (bounds[0] + bounds[1]) / 2
        diagonal = np.linalg.norm(bounds[1] - bounds[0])

        # Camera setup
        camera = pyrender.PerspectiveCamera(yfov=math.radians(45))
        distance = diagonal * 2.0

        # Position camera at 45 degree angle
        azimuth = math.radians(45)
        elevation = math.radians(25)

        cam_x = center[0] + distance * math.cos(elevation) * math.sin(azimuth)
        cam_y = center[1] + distance * math.sin(elevation)
        cam_z = center[2] + distance * math.cos(elevation) * math.cos(azimuth)

        # Look-at matrix
        eye = np.array([cam_x, cam_y, cam_z])
        target = center
        up = np.array([0, 1, 0])

        forward = target - eye
        forward = forward / np.linalg.norm(forward)
        right = np.cross(forward, up)
        right = right / np.linalg.norm(right)
        new_up = np.cross(right, forward)

        camera_pose = np.eye(4)
        camera_pose[:3, 0] = right
        camera_pose[:3, 1] = new_up
        camera_pose[:3, 2] = -forward
        camera_pose[:3, 3] = eye

        pr_scene.add(camera, pose=camera_pose)

        # Add lights
        # Key light
        key_light = pyrender.DirectionalLight(color=[1.0, 0.95, 0.9], intensity=3.0)
        key_pose = np.eye(4)
        key_pose[:3, 3] = [distance, distance * 0.8, distance * 0.5]
        pr_scene.add(key_light, pose=key_pose)

        # Fill light
        fill_light = pyrender.DirectionalLight(color=[0.8, 0.85, 1.0], intensity=1.5)
        fill_pose = np.eye(4)
        fill_pose[:3, 3] = [-distance * 0.5, distance * 0.3, distance]
        pr_scene.add(fill_light, pose=fill_pose)

        # Render
        renderer = pyrender.OffscreenRenderer(size, size)
        color, _ = renderer.render(pr_scene)
        renderer.delete()

        # Save as PNG
        image = Image.fromarray(color)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path, 'PNG')

        return True

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python glb_thumbnail_renderer.py <input_glb> <output_png> [size]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 150

    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    success = render_thumbnail(input_path, output_path, size)
    sys.exit(0 if success else 1)
