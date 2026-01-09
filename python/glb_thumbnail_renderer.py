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

        # Get bounds for camera positioning
        bounds = scene.bounds
        if bounds is None:
            print("Could not determine bounds", file=sys.stderr)
            return False

        center = (bounds[0] + bounds[1]) / 2
        extents = bounds[1] - bounds[0]
        max_extent = max(extents)

        if max_extent == 0:
            print("Model has zero extent", file=sys.stderr)
            return False

        # Create blank image with dark background
        img = Image.new('RGB', (size, size), color=(42, 48, 64))
        draw = ImageDraw.Draw(img)

        # Simple orthographic projection from 3/4 view
        # Rotate the scene for a nice viewing angle
        rotation = trimesh.transformations.euler_matrix(
            np.radians(25),  # pitch
            np.radians(45),  # yaw
            0  # roll
        )

        # Collect all faces and vertices from the scene
        all_faces = []
        vertex_offset = 0
        all_vertices = []
        all_z_depths = []  # For depth sorting faces

        for geometry in scene.geometry.values():
            if hasattr(geometry, 'vertices') and hasattr(geometry, 'faces'):
                verts = geometry.vertices.copy()

                # Center vertices
                verts -= center

                # Apply rotation
                verts_homogeneous = np.hstack([verts, np.ones((len(verts), 1))])
                rotated = verts_homogeneous @ rotation.T
                rotated_verts = rotated[:, :3]

                all_vertices.append(rotated_verts)

                # Adjust face indices
                faces = geometry.faces + vertex_offset
                all_faces.append(faces)

                vertex_offset += len(verts)

        if not all_vertices:
            print("No geometry found in model", file=sys.stderr)
            return False

        all_vertices = np.vstack(all_vertices)
        all_faces = np.vstack(all_faces) if all_faces else np.array([])

        # Scale to fit image with padding
        padding = 0.1
        scale = (size * (1 - 2 * padding)) / max_extent

        # Project to 2D (orthographic - just drop Z, but keep Z for depth sorting)
        points_2d = all_vertices[:, :2] * scale + size / 2
        z_depths = all_vertices[:, 2]

        # Colors for shading
        base_color = np.array([74, 158, 255])  # Blue color matching the UI
        dark_color = np.array([40, 80, 140])
        edge_color = (100, 140, 200)

        if len(all_faces) > 0:
            # Calculate face depths and normals for sorting and shading
            face_data = []
            for face in all_faces:
                v0, v1, v2 = all_vertices[face]
                # Face center depth (for sorting - draw back to front)
                face_depth = (z_depths[face[0]] + z_depths[face[1]] + z_depths[face[2]]) / 3

                # Calculate face normal for simple shading
                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = np.cross(edge1, edge2)
                normal_len = np.linalg.norm(normal)
                if normal_len > 0:
                    normal = normal / normal_len
                else:
                    normal = np.array([0, 0, 1])

                # Simple diffuse shading (light from camera direction)
                light_dir = np.array([0.3, 0.3, 1.0])
                light_dir = light_dir / np.linalg.norm(light_dir)
                shade = max(0.3, abs(np.dot(normal, light_dir)))

                face_data.append((face_depth, face, shade))

            # Sort faces by depth (back to front for painter's algorithm)
            face_data.sort(key=lambda x: x[0])

            # Draw filled faces
            for face_depth, face, shade in face_data:
                p0 = points_2d[face[0]]
                p1 = points_2d[face[1]]
                p2 = points_2d[face[2]]

                # Interpolate color based on shade
                color = (dark_color + (base_color - dark_color) * shade).astype(int)
                fill_color = tuple(color)

                # Draw filled triangle
                polygon = [(int(p0[0]), int(p0[1])),
                          (int(p1[0]), int(p1[1])),
                          (int(p2[0]), int(p2[1]))]
                draw.polygon(polygon, fill=fill_color, outline=edge_color)
        else:
            # Fallback to point cloud if no faces
            point_color = (180, 190, 200)
            for point in points_2d[::max(1, len(points_2d) // 1000)]:
                x, y = int(point[0]), int(point[1])
                if 0 <= x < size and 0 <= y < size:
                    draw.ellipse([x-1, y-1, x+1, y+1], fill=point_color)

        # Save the image
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG')

        print(f"Successfully rendered thumbnail with {len(all_faces)} faces", file=sys.stderr)
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
