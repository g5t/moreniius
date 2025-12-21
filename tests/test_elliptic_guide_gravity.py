import pytest
from nexusformat.nexus import NXguide


def make_elliptic_guide_instrument(use_explicit_ellipse_pars=False):
    """Create an instrument with an Elliptic_guide_gravity component."""
    from mccode_antlr import Flavor
    from mccode_antlr.assembler import Assembler

    inst = Assembler('elliptic_guide_test', flavor=Flavor.MCSTAS)

    inst.component('origin', 'Arm', at=(0, 0, 0))
    inst.component('source', 'Source_simple', at=[(0, 0, 0), 'origin'])

    if use_explicit_ellipse_pars:
        # Use explicit ellipse axis parameters
        inst.component(
            'elliptic_guide', 'Elliptic_guide_gravity',
            at=[(0, 0, 1), 'source'],
            parameters={
                'l': 2.0,
                'majorAxisxw': 1.5,
                'minorAxisxw': 0.05,
                'majorAxisoffsetxw': 0.5,
                'majorAxisyh': 1.5,
                'minorAxisyh': 0.06,
                'majorAxisoffsetyh': 0.5,
            }
        )
    else:
        # Use width/height based parameters with dimensionsAt
        inst.component(
            'elliptic_guide', 'Elliptic_guide_gravity',
            at=[(0, 0, 1), 'source'],
            parameters={
                'l': 2.0,
                'xwidth': 0.06,
                'yheight': 0.08,
                'linxw': 1.0,
                'loutxw': 1.0,
                'linyh': 1.0,
                'loutyh': 1.0,
                'dimensionsAt': '"mid"',
            }
        )

    return inst.instrument


def test_elliptic_guide_gravity_translator_from_widths():
    """Test the elliptic guide translator using width/height parameters."""
    import moreniius

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=False)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    assert me is not None
    assert 'elliptic_guide' in me.nx

    guide = me.nx['elliptic_guide']
    assert isinstance(guide, NXguide)

    # Should have OFF_GEOMETRY
    assert 'OFF_GEOMETRY' in guide


def test_elliptic_guide_gravity_translator_explicit_pars():
    """Test the elliptic guide translator using explicit ellipse axis parameters."""
    import moreniius

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=True)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    assert me is not None
    assert 'elliptic_guide' in me.nx

    guide = me.nx['elliptic_guide']
    assert isinstance(guide, NXguide)

    # Should have OFF_GEOMETRY
    assert 'OFF_GEOMETRY' in guide


def test_elliptic_guide_geometry_has_vertices_and_faces():
    """Test that the generated geometry has vertices and faces."""
    import moreniius

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=True)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    guide = me.nx['elliptic_guide']
    geometry = guide['OFF_GEOMETRY']

    # NXoff_geometry should have vertices, faces, and winding_order
    assert 'vertices' in geometry
    assert 'faces' in geometry
    assert 'winding_order' in geometry

    # Vertices should be a 2D array (n_vertices, 3)
    vertices = geometry['vertices'].nxdata
    assert vertices.ndim == 2
    assert vertices.shape[1] == 3

    # With n=10 segments, we should have 11 rings of 4 vertices each = 44 vertices
    assert vertices.shape[0] == 44


def test_elliptic_guide_nexus_structure():
    """Test that the elliptic guide is correctly represented in NeXus structure output."""
    import moreniius

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=True)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    ns = me.to_nexus_structure()

    # Navigate to the instrument level
    assert 'children' in ns
    entry = ns['children'][0]
    assert entry['name'] == 'entry'

    instrument = entry['children'][0]
    assert instrument['name'] == 'instrument'

    # Find the elliptic_guide component
    guide_groups = [c for c in instrument['children'] if c.get('name') == 'elliptic_guide']
    assert len(guide_groups) == 1

    guide = guide_groups[0]
    assert guide['type'] == 'group'

    # Check that it has the NXguide class attribute
    guide_attrs = guide.get('attributes', [])
    class_attrs = [a for a in guide_attrs if a.get('name') == 'NX_class']
    assert len(class_attrs) == 1
    assert class_attrs[0]['values'] == 'NXguide'


def test_ellipse_vertices_faces_function():
    """Test the _ellipse_vertices_faces helper function directly."""
    from moreniius.mccode.comp import _ellipse_vertices_faces

    major_x, minor_x, offset_x = 1.5, 0.05, 0.5
    major_y, minor_y, offset_y = 1.5, 0.06, 0.5
    l = 2.0
    n = 5

    vertices, faces = _ellipse_vertices_faces(
        major_x, minor_x, offset_x,
        major_y, minor_y, offset_y,
        l, n=n
    )

    # Should have (n+1) rings of 4 vertices each
    assert len(vertices) == (n + 1) * 4

    # Each ring creates 4 faces (top, bottom, left, right of guide)
    # For n segments, we have n * 4 faces
    assert len(faces) == n * 4

    # Each vertex should have 3 coordinates
    assert all(len(v) == 3 for v in vertices)

    # Each face should reference 4 vertex indices
    assert all(len(f) == 4 for f in faces)

    # z-coordinates should range from 0 to l
    z_coords = [v[2] for v in vertices]
    assert min(z_coords) == pytest.approx(0.0)
    assert max(z_coords) == pytest.approx(l)

