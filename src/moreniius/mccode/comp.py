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
    return nxinstance.make_nx(NXslit, x_gap=x_gap, y_gap=y_gap)


def guide_translator(nxinstance):
    from nexusformat.nexus import NXguide
    from moreniius.nxoff import NXoff
    off_pars = {k: nxinstance.nx_parameter(k) for k in ('l', 'w1', 'h1', 'w2', 'h2')}
    for k in ('w', 'h'):
        off_pars[f'{k}2'] = off_pars[f'{k}1'] if off_pars[f'{k}2'] == 0 else off_pars[f'{k}2']
    m_value = nxinstance.parameter('m')
    geometry = NXoff.from_wedge(**off_pars).to_nexus()
    return nxinstance.make_nx(NXguide, m_value=m_value, geometry=geometry)


def collimator_linear_translator(nxinstance):
    from nexusformat.nexus import NXcollimator
    from moreniius.nxoff import NXoff
    pars = {k: nxinstance.nx_parameter(v) for k, v in (('l', 'length'), ('w1', 'xwidth'), ('h1', 'yheight'))}
    return nxinstance.make_nx(NXcollimator, divergence_x=nxinstance.parameter('divergence'),
                        divergence_y=nxinstance.parameter('divergenceV'),
                        geometry=NXoff.from_wedge(**pars).to_nexus())


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
    return nxinstance.make_nx(NXdisk_chopper, slit_edges=NXfield(nx_slit_edges, units='degrees'), **pars)


def elliptic_guide_gravity_translator(nxinstance):
    from nexusformat.nexus import NXguide
    from numpy import arange, sqrt
    from moreniius.nxoff import NXoff
    if not '"mid"' == nxinstance.obj.get_parameter('dimensionsAt'):
        log.warn('Only midpoint geometry supported by Elliptic_guide_gravity translator')
        log.info(f'The current guide has {nxinstance.obj.get_parameter("dimensionsAt")} specified')

    def ellipse_width(minor, distance, at):
        major = sqrt((distance / 2) ** 2 + minor ** 2)
        return 0 if abs(at) > major else minor * sqrt(1 - (at / major) ** 2)

    pars = dict(xw='xwidth', xi='linxw', xo='loutxw', yw='yheight', yi='linyh', yo='loutyh', l='l')
    p = {k: nxinstance.parameter(v) for k, v in pars.items()}
    n = 10
    rings = arange(n + 1) / n
    faces, vertices = [], []
    for x in rings:
        w = ellipse_width(p['xw'] / 2, p['xi'] + p['l'] + p['xo'], p['xi'] / 2 + (x - 0.5) * p['l'] - p['xo'] / 2)
        h = ellipse_width(p['yw'] / 2, p['yi'] + p['l'] + p['yo'], p['yi'] / 2 + (x - 0.5) * p['l'] - p['yo'] / 2)
        z = x * p['l']
        vertices.extend([[-w, -h, z], [-w, h, z], [w, h, z], [w, -h, z]])

    for i in range(n):
        j0, j1, j2, j3, j4, j5, j6, j7 = [4 * i + k for k in range(8)]
        faces.extend([[j0, j1, j5, j4], [j1, j2, j6, j5], [j2, j3, j7, j6], [j3, j0, j4, j7]])

    nx_vertices = [[nxinstance.expr2nx(expr) for expr in vector] for vector in vertices]
    nx_faces = [[nxinstance.expr2nx(expr) for expr in face] for face in faces]

    return NXguide(geometry=NXoff(nx_vertices, nx_faces).to_nexus())


def monitor_translator(nxinstance):
    from nexusformat.nexus import NXmonitor
    from moreniius.nxoff import NXoff
    from moreniius.utils import NotNXdict
    from json import loads
    width = nxinstance.nx_parameter('xwidth')
    height = nxinstance.nx_parameter('yheight')
    geometry = NXoff.from_wedge(l=0.005, w1=width, h1=height)
    nx_monitor = NXmonitor(geometry=geometry.to_nexus())
    if len(nxinstance.obj.metadata):
        # look for mimetype 'application/json' and check if it is NeXus Structure data stream:
        for md in nxinstance.obj.metadata:
            if md.mimetype == 'application/json' and md.name == 'nexus_structure_stream_data':
                nx_monitor['data'] = NotNXdict(loads(md.value))

    return nx_monitor
