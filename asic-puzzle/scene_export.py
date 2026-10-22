"""Export notebook geometry for the article's interactive viewers."""

import gzip
import html
import json
import pathlib
import shutil

import numpy as np


def export_layers(groups, title, name):
    output = pathlib.Path('figs')
    output.mkdir(exist_ok=True)
    assets = pathlib.Path('.')
    for asset in ('viewer.js', 'viewer.css', 'viewer-layers.js'):
        shutil.copyfile(assets / asset, output / asset)
    layers = []
    low, high = np.full(2, np.inf), np.full(2, -np.inf)
    for (label, zlo, zhi, color), polygons in sorted(groups.items(), key=lambda item: item[0][1]):
        vertices = np.concatenate(polygons)
        low, high = np.minimum(low, vertices.min(0)), np.maximum(high, vertices.max(0))
        layers.append({'name': label, 'color': color,
                       'opacity': 0.8 if label.startswith('met') else 0.5,
                       'vertices': vertices.reshape(-1).tolist(),
                       'counts': [len(polygon) for polygon in polygons]})
    data = {'bounds': [*low, *high], 'layers': layers}
    packed = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    (output / f'{name}.scene.json.gz').write_bytes(gzip.compress(packed, mtime=0))
    (output / f'{name}.html').write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(title)}</title><link rel="stylesheet" href="viewer.css">'
        '<script defer src="viewer.js"></script><script defer src="viewer-layers.js"></script>'
        f'</head><body class="layer-view" data-scene="{html.escape(name, quote=True)}.scene.json.gz">'
        '<canvas id="layer-canvas" aria-label="Die conducting layers"></canvas>'
        '<div id="layer-legend" role="group" aria-label="Conducting layers"></div>'
        '<p id="scene-status" role="status">Loading conducting layers…</p></body></html>'
    )


def export_scene(plot, title, name, view_presets=None, readouts=None, net_ids=None, net_colors=None, simulation=None):
    output = pathlib.Path('figs')
    output.mkdir(exist_ok=True)
    assets = pathlib.Path('.')
    for asset in ('viewer.js', 'viewer.css', 'viewer-three.js', 'viewer-three.LICENSE'):
        shutil.copyfile(assets / asset, output / asset)

    def values(value):
        if isinstance(value, dict):
            return {key: values(array) for key, array in value.items()}
        return np.asarray(value).reshape(-1).tolist()

    objects = []
    for mesh in plot.objects:
        if mesh.type != 'Mesh':
            raise ValueError(f'Unsupported scene object: {mesh.type}')
        nets = np.asarray((net_ids or {}).get(mesh.id, []), dtype=np.int64)
        if nets.size and (len(nets) != len(mesh.vertices) or np.any(np.ptp(nets[mesh.indices], axis=1))):
            raise ValueError(f'Net IDs must identify every vertex and agree within each face: {mesh.name}')
        objects.append({
            'id': mesh.id, 'name': mesh.name, 'color': mesh.color,
            'opacity': mesh.opacity,
            'net_ids': nets.tolist(),
            **{key: values(getattr(mesh, key)) for key in
               ('vertices', 'indices', 'colors', 'attribute', 'color_map', 'color_range', 'model_matrix')},
        })
    data = {
        'camera': list(plot.camera), 'fov': plot.camera_fov,
        'objects': objects, 'hidden': list(plot.hidden_object_ids),
        'presets': view_presets or [], 'readouts': readouts or [],
        'net_colors': net_colors or {},
        'simulation': simulation,
    }
    packed = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    (output / f'{name}.scene.json.gz').write_bytes(gzip.compress(packed, mtime=0))
    (output / f'{name}.html').write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(title)}</title>'
        '<link rel="stylesheet" href="viewer.css">'
        '<script defer src="viewer.js"></script>'
        '<script defer src="viewer-three.js"></script></head>'
        f'<body class="three-view" data-scene="{html.escape(name, quote=True)}.scene.json.gz">'
        '<div id="scene-stage"></div><p id="scene-status" role="status">Loading 3D figure…</p>'
        '</body></html>'
    )
