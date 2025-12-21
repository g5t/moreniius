"""This file holds the default translators for a subset of Component types, used by NXInstance.

They can serve as a template for adding more translators, or replacing defaults, as needed.

A translator is a function that takes a component NXInstance and returns a valid NeXus object
for the _component type_ of that instance. The NXInstance holds a reference to the NXInstr object,
which can be used to look up values of identifier parameters, and the instance mccode_antlr.instr.Instance
object, which holds the instance's parameters and component type, among other information.

For a translator

def translator(nxinstance: NXInstance):
    ...

registering it as an attribute of the NXInstance class will make it available as a translator for
all instances of that class. For example:

NXInstance.SomeComponentTypeName = translator

or

NXInstance.SomeComponentTypeName = staticmethod(translator)

or

setattr(NXInstance, 'SomeComponentTypeName', translator)

will all work, even if added to the class after instances have been created.
(But since the translation is done automatically by __post_init__, it will not be applied to existing instances.)

A very nice possible enhancement to this approach would be to register each translator as a property
of the NXInstance class; then it can be used 'transparently' without needing to explicitly call it.
"""
from zenlog import log
from mccode_antlr.common import Expr
from moreniius.utils import resolve_parameter_links


def slit_translator(nxinstance):
    """The Slit component _must_ define (xmin, xmax) _or_ xwidth, and similarly the y-named parameters"""
    from nexusformat.nexus import NXslit
    if nxinstance.obj.defines_parameter('xwidth'):
        x_gap = nxinstance.parameter('xwidth')
        x_zero = Expr.float(0)
    else:
        x_gap = nxinstance.parameter('xmax') - nxinstance.parameter('xmin')
        x_zero = nxinstance.parameter('xmax') + nxinstance.parameter('xmin')
    if nxinstance.obj.defines_parameter('ywidth'):
        y_gap = nxinstance.parameter('ywidth')
        y_zero = Expr.float(0)
    else:
        y_gap = nxinstance.parameter('ymax') - nxinstance.parameter('ymin')
        y_zero = nxinstance.parameter('ymax') + nxinstance.parameter('ymin')

    if isinstance(x_zero, Expr) or isinstance(y_zero, Expr):
        log.warn(f'{nxinstance.obj.name} has a non-constant x or y zero, which requires special handling for NeXus')
    elif abs(x_zero) or abs(y_zero):
        log.warn(f'{nxinstance.obj.name} should be translated by [{x_zero}, {y_zero}, 0] via eniius_data METADATA')
    params = resolve_parameter_links(dict(x_gap=x_gap, y_gap=y_gap))
    return nxinstance.make_nx(NXslit, **params)


def guide_translator(nxinstance):
    from nexusformat.nexus import NXguide
    from moreniius.nxoff import NXoff
    off_pars = {k: nxinstance.nx_parameter(k) for k in ('l', 'w1', 'h1', 'w2', 'h2')}
    for k in ('w', 'h'):
        off_pars[f'{k}2'] = off_pars[f'{k}1'] if off_pars[f'{k}2'] == 0 else off_pars[f'{k}2']
    guide_pars = {'m_value': nxinstance.parameter('m')}
    geometry = NXoff.from_wedge(**off_pars).to_nexus()
    return nxinstance.make_nx(NXguide, OFF_GEOMETRY=geometry, **resolve_parameter_links(guide_pars))


def collimator_linear_translator(nxinstance):
    from nexusformat.nexus import NXcollimator
    from moreniius.nxoff import NXoff
    pars = {k: nxinstance.nx_parameter(v) for k, v in (('l', 'length'), ('w1', 'xwidth'), ('h1', 'yheight'))}
    col_pars = dict(divergence_x=nxinstance.parameter('divergence'), divergence_y=nxinstance.parameter('divergenceV'))
    return nxinstance.make_nx(NXcollimator, OFF_GEOMETRY=NXoff.from_wedge(**pars).to_nexus(),
                              **resolve_parameter_links(col_pars))


def diskchopper_translator(nxinstance):
    from nexusformat.nexus import NXdisk_chopper, NXfield
    mpars = {k: nxinstance.parameter(k) for k in ('nslit', 'nu', 'radius', 'theta_0', 'phase', 'yheight')}
    pars = {'slits': mpars['nslit'],
            'rotation_speed': nxinstance.make_nx(NXfield, mpars['nu'], units='Hz'),
            'radius': nxinstance.make_nx(NXfield, mpars['radius'], units='m'),
            'slit_angle': nxinstance.make_nx(NXfield, mpars['theta_0'], units='degrees'),
            'phase': nxinstance.make_nx(NXfield, mpars['phase'], units='degrees'),
            'slit_height': nxinstance.make_nx(NXfield, mpars['yheight'] if mpars['yheight'] else mpars['radius'], units='m')}
    nslit, delta = mpars['nslit'], mpars['theta_0'] / 2.0
    slit_edges = [y * 360.0 / nslit + x for y in range(int(nslit)) for x in (-delta, delta)]
    nx_slit_edges = [nxinstance.expr2nx(se) for se in slit_edges]
    return nxinstance.make_nx(NXdisk_chopper, slit_edges=NXfield(nx_slit_edges, units='degrees'), **resolve_parameter_links(pars))


def _ellipse_vertices_faces(major_x, minor_x, offset_x, major_y, minor_y, offset_y, l, n=10):
    """
    Create vertices and faces for an elliptical guide with given parameters.

    Parameters
    ----------
    major_x : float
        Major axis half-length in the x-direction.
    minor_x : float
        Minor axis half-length in the x-direction.
    offset_x : float
        Offset from the end of the ellipse to the guide entrance in the x-direction.
    major_y : float
        Major axis half-length in the y-direction.
    minor_y : float
        Minor axis half-length in the y-direction.
    offset_y : float
        Offset from the end of the ellipse to the guide entrance in the y-direction.
    l : float
        Length of the guide. l <= 2*major_x - offset_x and l <= 2*major_y - offset_y
    n : int, optional
        Number of segments along the length of the guide. Default is 10.
    """
    from numpy import arange, sqrt

    def ellipse_width(minor, major, at):
        return 0 if abs(at) > major else minor * sqrt(1 - (at / major) ** 2)

    rings = arange(n + 1) / n
    faces, vertices = [], []
    for x in rings:
        z = x * l
        w = ellipse_width(minor_x, major_x, offset_x - minor_x + z)
        h = ellipse_width(minor_y, major_y, offset_y - minor_y + x)

        vertices.extend([[-w, -h, z], [-w, h, z], [w, h, z], [w, -h, z]])

    # These are only the guide faces (that is, the inner faces of the sides of the guide housing)
    # The entry and exit are not guide faces and therefore are NOT represented here!
    for i in range(n):
        j0, j1, j2, j3, j4, j5, j6, j7 = [4 * i + k for k in range(8)]
        faces.extend([[j0, j1, j5, j4], [j1, j2, j6, j5], [j2, j3, j7, j6], [j3, j0, j4, j7]])

    return vertices, faces

def _ellipse_parameters_from_widths(nxinstance):
    from numpy import sqrt

    def parameters(which, w, i, o, l):
        foci = i + l + o
        offset = foci / 2 - i
        if 'mid' in which:
            minor = w / 2
            major = sqrt(foci ** 2 + minor ** 2) / 2
        else:
            t, b = (o, i) if 'entrance' in which else (i, o)
            t += l
            w /= 2
            b = sqrt(b * b + w * w / 4) + sqrt(t * t + w * w / 4)
            major = b / 2
            minor = sqrt(b * b - foci * foci) / 2
        return major, minor, offset

    pars = dict(xw='xwidth', xi='linxw', xo='loutxw', yw='yheight', yi='linyh', yo='loutyh', l='l')
    p = {k: nxinstance.parameter(v) for k, v in pars.items()}

    dim_at = str(nxinstance.obj.get_parameter('dimensionsAt').value)
    major_x, minor_x, offset_x = parameters(dim_at, p['xw'], p['xi'], p['xo'], p['l'])
    major_y, minor_y, offset_y = parameters(dim_at, p['yw'], p['yi'], p['yo'], p['l'])

    return major_x, minor_x, offset_x, major_y, minor_y, offset_y, p['l']


def elliptic_guide_gravity_translator(nxinstance):
    from nexusformat.nexus import NXguide
    from moreniius.nxoff import NXoff

    ellipse_pars = [f'{f}{s}' for f in ('majorAxis', 'minorAxis', 'majorAxisOffset') for s in ('xw', 'yh')]
    if all(nxinstance.obj.defines_parameter(p) for p in ellipse_pars):
        # we can use the specified ellipse parameters directly
        major_x = nxinstance.parameter('majorAxisxw')
        minor_x = nxinstance.parameter('minorAxisxw')
        offset_x = nxinstance.parameter('majorAxisOffsetxw')
        major_y = nxinstance.parameter('majorAxisyh')
        minor_y = nxinstance.parameter('minorAxisyh')
        offset_y = nxinstance.parameter('majorAxisOffsetyh')
        l = nxinstance.parameter('l')
    else:
        major_x, minor_x, offset_x, major_y, minor_y, offset_y, l = _ellipse_parameters_from_widths(nxinstance)

    vertices, faces = _ellipse_vertices_faces(major_x, minor_x, offset_x, major_y, minor_y, offset_y, l, n=10)

    nx_vertices = [[nxinstance.expr2nx(expr) for expr in vector] for vector in vertices]
    nx_faces = [[nxinstance.expr2nx(expr) for expr in face] for face in faces]

    return NXguide(OFF_GEOMETRY=NXoff(nx_vertices, nx_faces).to_nexus())


def monitor_translator(nxinstance):
    from nexusformat.nexus import NXmonitor, NXdata
    from moreniius.nxoff import NXoff
    from moreniius.utils import NotNXdict
    from json import loads
    width = nxinstance.nx_parameter('xwidth')
    height = nxinstance.nx_parameter('yheight')
    geometry = NXoff.from_wedge(l=0.005, w1=width, h1=height)
    nx_monitor = NXmonitor(OFF_GEOMETRY=geometry.to_nexus())
    if len(nxinstance.obj.metadata):
        # look for mimetype 'application/json' and check if it is NeXus Structure data stream:
        for md in nxinstance.obj.metadata:
            if md.mimetype == 'application/json' and md.name == 'nexus_structure_stream_data':
                nx_monitor['data'] = NXdata(data=NotNXdict(loads(md.value)))

    return nx_monitor
