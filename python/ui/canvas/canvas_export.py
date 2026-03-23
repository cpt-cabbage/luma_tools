"""
SQLite export/import for the collaborative canvas.

Exports canvas state as .luma files (SQLite database with optional embedded images).
Compatible with BeeRef .bee format structure using sqlar table.
"""

import os
import json
import logging
import sqlite3
import zlib
from pathlib import Path
from typing import Optional, Dict, Any, List

from core.utils import ensure_directory

logger = logging.getLogger(__name__)

# File extension
LUMA_EXTENSION = ".luma"


def export_to_luma(canvas_state: Dict[str, Any], output_path: str,
                   embed_images: bool = True, base_path: str = None) -> bool:
    """
    Export canvas state as .luma SQLite file.

    Args:
        canvas_state: Canvas state dict from get_state()
        output_path: Path to save the .luma file
        embed_images: If True, embed images in database; if False, keep paths
        base_path: Base path for relative paths (defaults to output_path parent)

    Returns:
        True if successful
    """
    try:
        # Ensure .luma extension
        if not output_path.lower().endswith(LUMA_EXTENSION):
            output_path += LUMA_EXTENSION

        base_path = base_path or os.path.dirname(output_path)

        # Remove existing file
        if os.path.exists(output_path):
            os.remove(output_path)

        # Create SQLite database
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()

        # Create tables
        _create_tables(cursor)

        # Store canvas metadata
        _store_metadata(cursor, canvas_state, embed_images)

        # Store nodes (images)
        for node_id, node_data in canvas_state.get('nodes', {}).items():
            _store_node(cursor, node_id, node_data, embed_images, base_path)

        # Store video nodes
        for node_id, node_data in canvas_state.get('videos', {}).items():
            _store_video(cursor, node_id, node_data, embed_images, base_path)

        # Store connections
        for conn_data in canvas_state.get('connections', []):
            _store_connection(cursor, conn_data)

        # Store annotations (sticky notes)
        for ann_data in canvas_state.get('annotations', []):
            _store_annotation(cursor, ann_data)

        # Store groups
        for group_data in canvas_state.get('groups', []):
            _store_group(cursor, group_data)

        # Store drawings if present
        for drawing_data in canvas_state.get('drawings', []):
            _store_drawing(cursor, drawing_data)

        conn.commit()
        conn.close()

        logger.info(f"Exported canvas to: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export canvas: {e}")
        return False


def import_from_luma(db_path: str, extract_path: str = None) -> Optional[Dict[str, Any]]:
    """
    Import canvas state from .luma SQLite file.

    Args:
        db_path: Path to the .luma file
        extract_path: Path to extract embedded images (defaults to same dir)

    Returns:
        Canvas state dict, or None if failed
    """
    conn = None
    try:
        if not os.path.exists(db_path):
            logger.error(f"File not found: {db_path}")
            return None

        extract_path = extract_path or os.path.dirname(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Load metadata
        cursor.execute("SELECT key, value FROM metadata")
        metadata = {row[0]: row[1] for row in cursor.fetchall()}

        embed_images = metadata.get('embed_images', 'true') == 'true'
        state_json = metadata.get('canvas_state', '{}')

        state = json.loads(state_json)

        # Load nodes with embedded images
        cursor.execute("SELECT node_id, data FROM nodes")
        nodes = {}
        for node_id, data_json in cursor.fetchall():
            node_data = json.loads(data_json)

            # Extract embedded image if present
            if embed_images:
                image_path = _extract_embedded_image(cursor, node_id, extract_path)
                if image_path:
                    node_data['path'] = image_path

            nodes[node_id] = node_data

        state['nodes'] = nodes

        # Load video nodes
        try:
            cursor.execute("SELECT node_id, data FROM videos")
            videos = {}
            for node_id, data_json in cursor.fetchall():
                node_data = json.loads(data_json)
                if embed_images:
                    # Videos use prefixed sqlar key to avoid collisions with images
                    video_path = _extract_embedded_image(
                        cursor, f"video_{node_id}", extract_path)
                    if video_path:
                        node_data['path'] = video_path
                videos[node_id] = node_data
            state['videos'] = videos
        except sqlite3.OperationalError:
            # Table may not exist in older .luma files
            state['videos'] = {}

        # Load connections
        cursor.execute("SELECT data FROM connections")
        state['connections'] = [json.loads(row[0]) for row in cursor.fetchall()]

        # Load annotations
        cursor.execute("SELECT data FROM annotations")
        state['annotations'] = [json.loads(row[0]) for row in cursor.fetchall()]

        # Load groups
        cursor.execute("SELECT data FROM groups")
        state['groups'] = [json.loads(row[0]) for row in cursor.fetchall()]

        # Load drawings
        try:
            cursor.execute("SELECT data FROM drawings")
            state['drawings'] = [json.loads(row[0]) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Table may not exist in older .luma files
            state['drawings'] = []

        logger.info(f"Imported canvas from: {db_path}")
        return state

    except Exception as e:
        logger.error(f"Failed to import canvas: {e}")
        return None
    finally:
        if conn:
            conn.close()


def _create_tables(cursor):
    """Create the database tables."""
    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Nodes (images) table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            data TEXT
        )
    """)

    # Embedded images table (sqlar format for compatibility with BeeRef)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sqlar (
            name TEXT PRIMARY KEY,
            mode INT,
            mtime INT,
            sz INT,
            data BLOB
        )
    """)

    # Connections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT
        )
    """)

    # Annotations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT
        )
    """)

    # Groups table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT
        )
    """)

    # Videos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            node_id TEXT PRIMARY KEY,
            data TEXT
        )
    """)

    # Drawings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drawings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT
        )
    """)


def _store_metadata(cursor, canvas_state: dict, embed_images: bool):
    """Store canvas metadata."""
    # Version info
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('version', '1.0'))
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('format', 'luma'))
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('embed_images', 'true' if embed_images else 'false'))

    # Store viewport state
    viewport = canvas_state.get('viewport', {})
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('viewport_x', str(viewport.get('x', 0))))
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('viewport_y', str(viewport.get('y', 0))))
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('viewport_zoom', str(viewport.get('zoom', 1.0))))

    # Store full state as JSON backup
    cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                   ('canvas_state', json.dumps(canvas_state)))


def _store_node(cursor, node_id: str, node_data: dict, embed_images: bool, base_path: str):
    """Store a node and optionally embed its image."""
    # Store node data
    cursor.execute("INSERT INTO nodes VALUES (?, ?)",
                   (node_id, json.dumps(node_data)))

    # Embed image if requested
    if embed_images:
        image_path = node_data.get('path', '')
        if image_path and os.path.exists(image_path):
            _embed_image(cursor, node_id, image_path)


def _store_video(cursor, node_id: str, node_data: dict, embed_images: bool, base_path: str):
    """Store a video node and optionally embed the video file."""
    cursor.execute("INSERT INTO videos VALUES (?, ?)",
                   (node_id, json.dumps(node_data)))

    # Embed video if requested (same sqlar mechanism as images)
    if embed_images:
        video_path = node_data.get('path', '')
        if video_path and os.path.exists(video_path):
            _embed_image(cursor, f"video_{node_id}", video_path)


def _embed_image(cursor, node_id: str, image_path: str):
    """Embed an image in the sqlar table."""
    try:
        with open(image_path, 'rb') as f:
            data = f.read()

        # Compress with zlib
        compressed = zlib.compress(data)

        stat = os.stat(image_path)
        cursor.execute(
            "INSERT OR REPLACE INTO sqlar VALUES (?, ?, ?, ?, ?)",
            (node_id, stat.st_mode, int(stat.st_mtime), len(data), compressed)
        )
        logger.debug(f"Embedded image: {image_path} ({len(data)} -> {len(compressed)} bytes)")

    except Exception as e:
        logger.warning(f"Failed to embed image {image_path}: {e}")


def _extract_embedded_image(cursor, node_id: str, extract_path: str) -> Optional[str]:
    """Extract an embedded image from the sqlar table."""
    try:
        cursor.execute("SELECT sz, data FROM sqlar WHERE name = ?", (node_id,))
        row = cursor.fetchone()
        if not row:
            return None

        original_size, compressed_data = row

        # Decompress
        data = zlib.decompress(compressed_data)

        # Determine extension from data (images and videos)
        ext = '.png'  # Default
        if data[:2] == b'\xff\xd8':
            ext = '.jpg'
        elif data[:4] == b'RIFF':
            ext = '.webp'
        elif data[:4] == b'GIF8':
            ext = '.gif'
        elif data[4:8] == b'ftyp':
            ext = '.mp4'
        elif data[:4] == b'\x1a\x45\xdf\xa3':
            ext = '.webm'

        # Save to extract path
        filename = f"{node_id}{ext}"
        output_path = os.path.join(extract_path, filename)
        ensure_directory(extract_path)

        with open(output_path, 'wb') as f:
            f.write(data)

        logger.debug(f"Extracted image: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Failed to extract image {node_id}: {e}")
        return None


def _store_connection(cursor, conn_data: dict):
    """Store a connection."""
    cursor.execute("INSERT INTO connections (data) VALUES (?)",
                   (json.dumps(conn_data),))


def _store_annotation(cursor, ann_data: dict):
    """Store an annotation."""
    cursor.execute("INSERT INTO annotations (data) VALUES (?)",
                   (json.dumps(ann_data),))


def _store_group(cursor, group_data: dict):
    """Store a group."""
    cursor.execute("INSERT INTO groups (data) VALUES (?)",
                   (json.dumps(group_data),))


def _store_drawing(cursor, drawing_data: dict):
    """Store a drawing."""
    cursor.execute("INSERT INTO drawings (data) VALUES (?)",
                   (json.dumps(drawing_data),))


def get_luma_info(db_path: str) -> Optional[Dict[str, Any]]:
    """
    Get information about a .luma file without fully loading it.

    Args:
        db_path: Path to the .luma file

    Returns:
        Dict with file info, or None if failed
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get metadata
        cursor.execute("SELECT key, value FROM metadata")
        metadata = {row[0]: row[1] for row in cursor.fetchall()}

        # Count items
        cursor.execute("SELECT COUNT(*) FROM nodes")
        node_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM connections")
        conn_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM annotations")
        ann_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sqlar")
        embedded_count = cursor.fetchone()[0]

        conn.close()

        return {
            'version': metadata.get('version', 'unknown'),
            'embed_images': metadata.get('embed_images', 'false') == 'true',
            'node_count': node_count,
            'connection_count': conn_count,
            'annotation_count': ann_count,
            'embedded_images': embedded_count,
            'viewport': {
                'x': float(metadata.get('viewport_x', 0)),
                'y': float(metadata.get('viewport_y', 0)),
                'zoom': float(metadata.get('viewport_zoom', 1.0)),
            }
        }

    except Exception as e:
        logger.error(f"Failed to get luma info: {e}")
        return None
