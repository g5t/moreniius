from zenlog import log
from dataclasses import dataclass, field
from mccode_antlr.instr import Orient
from .instr import NXInstr

log.level('error')


@dataclass
class NXMcCode:
    nx_instr: NXInstr
    origin_name: str = None
    indexes: dict[str, int] = field(default_factory=dict)
    orientations: dict[str, Orient] = field(default_factory=dict)

    def __post_init__(self):
        from copy import deepcopy
        for index, instance in enumerate(self.nx_instr.instr.components):
            self.indexes[instance.name] = index
            self.orientations[instance.name] = deepcopy(instance.orientation)
        # Attempt to re-center all component dependent orientations on the sample
        found = (lambda x: self.origin_name == x.name) if self.origin_name else (lambda x: 'samples' == x.type.category)
        possible_origins = [instance for instance in self.nx_instr.instr.components if found(instance)]

        if not possible_origins:
            msg = '"sample" category components' if self.origin_name is None else f'component named {self.origin_name}'
            log.warn(f'No {msg} in instrument, using ABSOLUTE positions')
        elif self.origin_name is not None and len(possible_origins) > 1:
            log.error(f'{len(possible_origins)} components named {self.origin_name}; using the first')
        elif len(possible_origins) > 1:
            log.warn(f'More than one "sample" category component. Using {possible_origins[0].name} for origin name')
        if possible_origins:
            self.origin_name = possible_origins[0].name
            # find the position _and_ rotation of the origin
            origin = possible_origins[0].orientation
            # remove this from all components (re-centering on the origin)
            for name in self.orientations:
                self.orientations[name] = self.orientations[name] - origin

    def transformations(self, name):
        from .orientation import NXOrient
        return NXOrient(self.nx_instr, self.orientations[name]).transformations(name)

    def component(self, name, only_nx=True):
        """Return a NeXus NXcomponent corresponding to the named McStas component instance"""
        from .instance import NXInstance
        instance = self.nx_instr.instr.components[self.indexes[name]]
        transformations = self.transformations(name)
        nx = NXInstance(self.nx_instr, instance, self.indexes[name], transformations, only_nx=only_nx)
        if transformations and nx.nx['transformations'] != transformations:
            # if the component modifed the transformations group, make sure we don't use our version again
            del self.orientations[name]
        return nx

    def instrument(self, only_nx=True):
        from .instr import NXInstr
        from nexusformat.nexus import NXinstrument
        nx = NXinstrument()  # this is a NeXus class
        nx['mcstas'] = self.nx_instr.to_nx()
        for name in self.indexes:
            nx[name] = self.component(name, only_nx=only_nx).nx

        return nx
