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
    from moreniius import NexusStructureNavigator

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=True)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    ns_dict = me.to_nexus_structure()
    
    # Use navigator for cleaner access
    nav = NexusStructureNavigator(ns_dict)

    # Navigate to entry and instrument
    entry = nav['entry']
    assert entry.structure['name'] == 'entry'

    instrument = nav['entry']['instrument']
    assert instrument.structure['name'] == 'instrument'

    # Access the elliptic_guide component directly by name
    guide = nav['entry']['instrument']['elliptic_guide']
    assert guide.structure['type'] == 'group'

    # Check that it has the NXguide class attribute using navigator
    nx_class_attr = guide['@NX_class']
    assert nx_class_attr['values'] == 'NXguide'


def test_ellipse_vertices_faces_function():
    """Test the _ellipse_vertices_faces helper function directly."""
    from moreniius.mccode.comp import _ellipse_vertices_faces

    major_x, minor_x, offset_x = 1.5, 0.05, 0.5
    major_y, minor_y, offset_y = 1.5, 0.06, 0.5
    l = 2.0
    n = 5
    m_left, m_top, m_right, m_bottom = 1., 2., 3., 4.

    vertices, faces, m_values = _ellipse_vertices_faces(
        major_x=major_x, minor_x=minor_x, offset_x=offset_x,
        major_y=major_y, minor_y=minor_y, offset_y=offset_y,
        m_left=m_left, m_top=m_top, m_right=m_right, m_bottom=m_bottom,
        l=l, n=n
    )

    # Should have (n+1) rings of 4 vertices each
    assert len(vertices) == (n + 1) * 4

    # Each ring creates 4 faces (top, bottom, left, right of guide)
    # For n segments, we have n * 4 faces
    assert len(faces) == n * 4

    assert len(m_values) == n * 4, "Length of faces and m_values must match"

    # Each vertex should have 3 coordinates
    assert all(len(v) == 3 for v in vertices)

    # Each face should reference 4 vertex indices
    assert all(len(f) == 4 for f in faces)

    # z-coordinates should range from 0 to l
    z_coords = [v[2] for v in vertices]
    assert min(z_coords) == pytest.approx(0.0)
    assert max(z_coords) == pytest.approx(l)

    for i in range(n):
        assert m_values[i*4:(i+1)*4] == [m_left, m_top, m_right, m_bottom]


def test_elliptic_guide_m_values_are_default():
    import moreniius
    from numpy import allclose

    instr = make_elliptic_guide_instrument(use_explicit_ellipse_pars=True)
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    guide = me.nx['elliptic_guide']
    m_values = guide['m_value']
    assert m_values.ndim == 1
    assert m_values.shape[0] % 4 == 0
    assert allclose(m_values, 2.0), "The in-component default is m=2.0"


def test_guide_m_value_has_units():
    """Test that the guide m_value dataset has a units attribute (issue #41)."""
    from mccode_antlr import Flavor
    from mccode_antlr.assembler import Assembler
    import moreniius

    # Create an instrument with a regular Guide_gravity component
    inst = Assembler('guide_test', flavor=Flavor.MCSTAS)
    inst.component('origin', 'Arm', at=(0, 0, 0))
    inst.component('source', 'Source_simple', at=[(0, 0, 0), 'origin'])
    inst.component(
        'guide', 'Guide_gravity',
        at=[(0, 0, 1), 'source'],
        parameters={
            'w1': 0.1, 'h1': 0.1, 'w2': 0.1, 'h2': 0.1,
            'l': 2.0, 'm': 1.5
        }
    )
    
    instr = inst.instrument
    me = moreniius.MorEniius.from_mccode(
        instr, origin='origin', only_nx=False, absolute_depends_on=True
    )

    guide = me.nx['guide']
    assert isinstance(guide, NXguide)

    # The guide should have an m_value dataset
    assert 'm_value' in guide, "Guide should have m_value dataset"
    
    # The m_value should have a units attribute (issue #41)
    m_value = guide['m_value']
    assert hasattr(m_value, 'attrs'), "m_value should have attributes"
    assert 'units' in m_value.attrs, "m_value should have a units attribute"
    # According to issue #41, it should be dimensionless (empty string or 'dimensionless')
    assert m_value.attrs['units'] in ('', 'dimensionless'), f"m_value units should be dimensionless, got {m_value.attrs['units']}"

