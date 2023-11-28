from zenlog import log
from dataclasses import dataclass
from typing import Union
from mccode_antlr.instr import Instance
from mccode_antlr.common import Expr
from nexusformat.nexus import NXfield
from .instr import NXInstr


COMPONENT_GROUP_TO_NEXUS = dict(Guide='NXguide', Collimator='NXcollimator')
COMPONENT_CATEGORY_TO_NEXUS = dict(sources='NXmoderator', monitors='NXdetector')
COMPONENT_TYPE_NAME_TO_NEXUS = dict(
    DiskChopper='NXdisk_chopper',
    FermiChopper='NXfermi_chopper',
    FermiChopper_ILL='NXfermi_chopper',
    Fermi_chop2a='NXfermi_chopper',
    Filter_gen='NXfilter',
    Filter_graphite='NXfilter',
    Elliptic_guide_gravity='NXguide',
    Mirror='NXmirror',
    Monochromator_flat='NXmonochromator',
    Monochromator_curved='NXmonochromator',
    Monochromator_pol='NXpolarizer',
    Pol_SF_ideal='NXflipper',
    Pol_bender='NXpolarizer',
    Pol_mirror='NXpolarizer',
    SNS_source='NXmoderator',
    SNS_source_analytic='NXmoderator',
    Source_pulsed='NXmoderator',
    Selector='NXvelocity_selector',
    V_selector='NXvelocity_selector',
    ViewModISIS='NXmoderator',
)
# Each entry here maps a NeXus component to a McStas component
# The second element is a mapping of NeXus component parameters to McStas parameters
# The third element is a mapping of NeXus component parameters to McStas position paramters
NEXUS_TO_COMPONENT = dict(
    NXdetector=['Monitor_nD', {}, ],
    NXdisk_chopper=['DiskChopper',
                    {'slits': 'nslit',
                     'rotation_speed': 'nu',
                     'radius': 'radius',
                     'slit_angle': 'theta_0',
                     'slit_height': 'yheight',
                     'phase': 'phase'},
                    ],
    NXfermi_chopper=['FermiChopper',
                     {'rotation_speed': 'nu',
                      'radius': 'radius',
                      'slit': 'w',
                      'r_slit': 'curvature',
                      'number': 'nslit',
                      'width': 'xwidth',
                      'height': 'yheight'
                      },
                     {'distance': 'set_AT'
                      },
                     ],
    NXsample=['Incoherent', {}, ],
    NXmoderator=['Moderator', {}, {'distance': 'set_AT'}, ]
)


@dataclass
class NXInstance:
    instr: NXInstr
    obj: Instance
    index: int
    transforms: dict[str, NXfield]
    only_nx: bool
    nx: Union[None, dict, NXfield] = None

    def parameter(self, name):
        """
        Pull out a named instance parameter -- if it's value is not a constant, attempt to evaluate it
        using the Instr declare and initialize sections
        """
        par = self.obj.get_parameter(name)
        if par is None:
            log.warn(f'It appears that {self.obj.type.name} does not define the parameter {name}')
            return None

        expr = par.value
        # log.info(f'get parameter {name} which is {par}  and expr {repr(expr)}')
        if expr.is_constant:
            return expr.value

        # Check if the expression depends on one of the instrument parameters (and thus needs a NXlog stream)
        # First resolve any declare-variables
        evaluated = expr.evaluate(self.instr.declared)
        if evaluated.is_constant:
            return evaluated.value
        # Then check for instrument parameter(s)
        dependencies = [par for par in self.instr.instr.parameters if evaluated.depends_on(par.name)]
        log.warn(f'The parameter {name} for component instance {self.obj.name} '
                 f' depends on an instrument parameter and has value {expr}')
        return evaluated

    def expr2nx(self, expr: Expr):
        return self.instr.expr2nx(expr)

    def nx_parameter(self, name):
        """Retrieve the named instance parameter and convert to a NeXus compatible value"""
        return self.expr2nx(self.parameter(name))

    def make_nx(self, nx_class, *args, **kwargs):
        return self.instr.make_nx(nx_class, *args, **kwargs)

    def __post_init__(self):
        from json import dumps
        from nexusformat.nexus import NXtransformations
        from moreniius.utils import outer_transform_dependency, mccode_component_eniius_data
        self.nx = getattr(self, self.obj.type.name, self.default_translation)()
        self.nx['mcstas'] = dumps({'instance': str(self.obj), 'order': self.index})
        if self.transforms:
            self.nx['transformations'] = NXtransformations(**self.transforms)
            most_dependent = outer_transform_dependency(self.nx['transformations'])
            for name, insert in mccode_component_eniius_data(self.obj, only_nx=self.only_nx).items():
                self.nx[name] = insert
                if not hasattr(self.nx[name], 'depends_on'):
                    self.nx[name].attrs['depends_on'] = most_dependent
                most_dependent = outer_transform_dependency(self.nx['transformations'])
            self.nx['depends_on'] = f'transformations/{most_dependent}'

    def get_nx_type(self):
        if self.obj.type.name in COMPONENT_TYPE_NAME_TO_NEXUS:
            return COMPONENT_TYPE_NAME_TO_NEXUS[self.obj.type.name]
        elif self.obj.type.category in COMPONENT_CATEGORY_TO_NEXUS:
            return COMPONENT_CATEGORY_TO_NEXUS[self.obj.type.category]
        if any(self.obj.type.name.startswith(x) for x in COMPONENT_GROUP_TO_NEXUS):
            return [t for k, t in COMPONENT_GROUP_TO_NEXUS.items() if self.obj.type.name.startswith(k)][0]
        return 'NXnote'

    def default_translation(self):
        import nexusformat.nexus as nexus
        nx_type = self.get_nx_type()
        nx_2_mc = NEXUS_TO_COMPONENT.get(nx_type, ({}, {}))[1]
        return getattr(nexus, nx_type)(**{n: self.nx_parameter(m) for n, m in nx_2_mc.items()})


def register_translator(name, translator):
    """After the normal __init__ method instantiates a NXInstance object, the __post_init__ method is used
    to translate its held mccode_antlr.instr.Instance object into a NeXus object. This is done by calling
    the translator function registered for the component type name.
    It is not feasible to register a translator for every possible component type, so this function can be used
    to add translators for specific component types that you, the user, need for your instrument.

    Your translator must be a function with one input, the NXInstance object, and one output, a NeXus object.
    After you have defined your translator function, you can register it with this function.

    >>> import eniius
    >>>
    >>> def my_translator(instance):
    >>>     from nexusformat.nexus import NXguide
    >>>     return instance.make_nx(NXguide, m_value=instance.parameter('m'))
    >>>
    >>> moreniius.mccode.instance.register_translator('MyComponentType', my_translator)
    """
    setattr(NXInstance, name, translator)


def register_default_translators():
    from .comp import (slit_translator, guide_translator, collimator_linear_translator,
                       diskchopper_translator, elliptic_guide_gravity_translator,
                       monitor_translator)
    for name, translator in (('Slit', slit_translator),
                             ('Guide', guide_translator),
                             ('Guide_channeled', guide_translator),
                             ('Guide_gravity', guide_translator),
                             ('Guide_simple', guide_translator),
                             ('Guide_wavy', guide_translator),
                             ('Collimator_linear', collimator_linear_translator),
                             ('DiskChopper', diskchopper_translator),
                             ('Elliptic_guide_gravity', elliptic_guide_gravity_translator),
                             ('TOF_monitor', monitor_translator),
                             ('PSD_monitor', monitor_translator),):
        register_translator(name, translator)


register_default_translators()
