"""
Standalone GLB thumbnail renderer using PIL/Pillow for rendering.

This script runs as a separate process to avoid OpenGL context conflicts with Qt.
It renders a GLB/GLTF file to a PNG thumbnail by creating a simple orthographic projection.

Usage:
    python glb_thumbnail_renderer.py <input_glb_path> <output_png_path> [size]
"""

import sys
import os

def render_thumbnail(glb_path: str, output_path: str, size: int = 150) -> bool:
    """
    Render a GLB file to a PNG thumbnail.

    Args:
        glb_path: Path to the GLB/GLTF file
        output_path: Path to save the PNG thumbnail
        size: Size of the square thumbnail (in pixels)

    Returns:
        True if successful, False otherwise
    """
    try:
        import trimesh
        import numpy as np
        from PIL import Image, ImageDraw
        
        # Load the model
        scene_or_mesh = trimesh.load(glb_path)
        
        # Get the scene (convert single mesh to scene if needed)
        if isinstance(scene_or_mesh, trimesh.Trimesh):
            scene = trimesh.Scene(scene_or_mesh)
        else:
            scene = scene_or_mesh
        
        # Use simple wireframe/point cloud rendering (no OpenGL/windowing required)
        print("Using headless point cloud rendering", file=sys.stderr)
        
        # Get bounds for camera positioning
        bounds = scene.bounds
        if bounds is None:
            print("Could not determine bounds", file=sys.stderr)
            return False
        
        center = (bounds[0] + bounds[1]) / 2
        extents = bounds[1] - bounds[0]
        max_extent = max(extents)
        
        # Create blank image with dark background
        img = Image.new('RGB', (size, size), color=(41, 46, 56))
        draw = ImageDraw.Draw(img)
        
        # Simple orthographic projection from 3/4 view
        # Rotate the scene for a nice viewing angle
        rotation = trimesh.transformations.euler_matrix(
            np.radians(25),  # pitch
            np.radians(45),  # yaw  
            0  # roll
        )
        
        # Get all vertices from the scene
        vertices = []
        for geometry in scene.geometry.values():
            if hasattr(geometry, 'vertices'):
                # Apply rotation
                verts = geometry.vertices.copy()
                verts_homogeneous = np.hstack([verts, np.ones((len(verts), 1))])
                rotated = verts_homogeneous @ rotation.T
                vertices.append(rotated[:, :3])
        
        if not vertices:
            print("No vertices found in model", file=sys.stderr)
            return False
        
        all_vertices = np.vstack(vertices)
        
        # Center the vertices
        all_vertices -= center
        
        # Project to 2D (orthographic - just drop Z)
        points_2d = all_vertices[:, :2]
        
        # Scale to fit image with padding
        padding = 0.1
        scale = (size * (1 - 2 * padding)) / max_extent
        points_2d *= scale
        
        # Center in image
        points_2d += size / 2
        
        # Draw points as small circles to create a point cloud effect
        point_color = (180, 190, 200)  # Light gray
        for point in points_2d[::max(1, len(points_2d) // 1000)]:  # Sample points if too many
            x, y = int(point[0]), int(point[1])
            if 0 <= x < size and 0 <= y < size:
                draw.ellipse([x-1, y-1, x+1, y+1], fill=point_color)
        
        # Save the image
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG')
        
        print(f"Successfully rendered fallback thumbnail", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"Rendering failed: {e}", file=sys.stderr)
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
