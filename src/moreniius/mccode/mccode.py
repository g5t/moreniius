from nexusformat.nexus import NXfield
from zenlog import log
from dataclasses import dataclass, field
from networkx import DiGraph
from typing import Union
from mccode_antlr.instr import Orient
from .instr import NXInstr

log.level('error')

@dataclass
class NXMcCode:
    nx_instr: NXInstr
    origin_name: Union[str, None] = None
    indexes: dict[str, int] = field(default_factory=dict)
    orientations: dict[str, Orient] = field(default_factory=dict)
    graph: Union[DiGraph, None] = None
    reversed_graph: Union[DiGraph, None] = None

    def __post_init__(self):
        from copy import deepcopy

        for index, instance in enumerate(self.nx_instr.instr.components):
            self.indexes[instance.name] = index
            # only absolute-positioned or rotated component orientations are needed
            if instance.at_relative[1] is None or instance.rotate_relative[1] is None:
                self.orientations[instance.name] = deepcopy(instance.orientation)

        # Attempt to re-center all component dependent orientations on the sample
        found = (
            (lambda x: self.origin_name == x.name)
            if self.origin_name else
            (lambda x: 'samples' == x.type.category)
        )
        possible_origins = [instance for instance in
                            self.nx_instr.instr.components if found(instance)]
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
            # remove this from all (absolute) components (re-centering on the origin)
            for name, orientation in self.orientations.items():
                self.orientations[name] = orientation - origin

        if self.graph is None:
            self.graph = self.build_graph()
        if self.reversed_graph is None:
            self.reversed_graph = self.graph.reverse(copy=True)

    def transformations(self, name) -> dict[str, NXfield]:
        from mccode_antlr.instr.orientation import Vector, Angles, Parts
        from .orientation import NXOrient, NXParts

        def abs_ref(ref):
            # FIXME find a better way to ensure this is correct
            return f'/entry/instrument/{ref}'

        def last_ref(refs: list[tuple[str, NXfield]]) -> str | None:
            try:
                return next(reversed(refs))[0]
            except StopIteration:
                pass

        at_vec, at_rel = self.nx_instr.instr.components[self.indexes[name]].at_relative
        rot_ang, rot_rel = self.nx_instr.instr.components[self.indexes[name]].rotate_relative

        nx_orientation = None
        if at_rel is None or rot_rel is None:
            nx_orientation = NXOrient(self.nx_instr, self.orientations[name])

        if at_rel is None and rot_rel is None:
            # ABSOLUTE definition, so we pull information from self.orientations
            # since we had to remove the (possibly different) origin
            return nx_orientation.transformations(name)

        trans = []
        if at_rel is not None and rot_rel is not None and at_rel == rot_rel:
            at_vec = Vector(*at_vec) if isinstance(at_vec, tuple) else at_vec
            rot_ang = Angles(*rot_ang) if isinstance(rot_ang, tuple) else rot_ang
            at_parts = Parts.from_at_rotated(at_vec, Angles(), True)
            rot_parts = Parts.from_at_rotated(Vector(), rot_ang, True)
            nx_parts = NXParts(self.nx_instr, at_parts, rot_parts)
            trans.extend(nx_parts.transformations(name, abs_ref(at_rel.name)))
        else:
            raise RuntimeError("All mixed reference-type orientations untested. "
                               "Only 'AT (x, y, z) ABSOLUTE ROTATE (a, b, c) REF' might work")
        # elif at_rel is None:
        #     # absolute position with relative rotation
        #     trans.extend(nx_orientation.position_transformations(name))
        #     # Get the _rotation_ of the reference to add here before any new rotation
        #     # FIXME this can only work if rot_rel.name is in self.orientations!
        #     rel_ori = NXOrient(self.nx_instr, self.orientations[rot_rel.name])
        #     trans.extend(rel_ori.rotation_transformations(rot_rel.name, last_ref(trans)))
        #     # Now add our relative rotation onto the referenced rotation
        #     rot_ang = Angles(*rot_ang) if isinstance(rot_ang, tuple) else rot_ang
        #     rot = Parts(Parts.from_at_rotated(Vector(), rot_ang, True).stack()).reduce()
        #     nx_parts = NXParts(self.nx_instr, rot, rot)
        #     trans.extend(nx_parts.rotation_transformations(name, last_ref(trans)))
        # elif rot_rel is None:
        #     # relative position with absolute rotations
        #     raise RuntimeError("I can not handle this yet")
        # else:
        #     # relative position and rotation but different references.
        #     raise RuntimeError("I cnat no handle this ytet")

        return {k: v for k, v in trans}

    def inputs(self, name):
        """Return the other end of edges ending at the named node"""
        return list(self.reversed_graph[name])

    def outputs(self, name):
        """Return the other end of edges starting at the named node"""
        return list(self.graph[name])

    def component(self, name, only_nx=True):
        """Return a NeXus NXcomponent corresponding to the named McStas component instance"""
        from .instance import NXInstance
        instance = self.nx_instr.instr.components[self.indexes[name]]
        transformations = self.transformations(name)
        nxinst = NXInstance(self.nx_instr, instance, self.indexes[name], transformations, only_nx=only_nx)
        if transformations and nxinst.nx['transformations'] != transformations and name in self.orientations:
            # if the component modifed the transformations group, make sure we don't use our version again
            del self.orientations[name]
        if len(inputs := self.inputs(name)):
            nxinst.nx.attrs['inputs'] = inputs
        if len(outputs := self.outputs(name)):
            nxinst.nx.attrs['outputs'] = outputs
        return nxinst

    def instrument(self, only_nx=True):
        from nexusformat.nexus import NXinstrument
        nx = NXinstrument()  # this is a NeXus class
        nx['mcstas'] = self.nx_instr.to_nx()
        for name in self.indexes.keys():
            nx[name] = self.component(name, only_nx=only_nx).nx

        return nx

    def build_graph(self):
        # FIXME expand this to a full-description if/when McCode includes graph information
        graph = DiGraph()
        names = [x.name for x in self.nx_instr.instr.components]
        graph.add_nodes_from(names)
        # By default, any McCode instrument is a linear object:
        graph.add_edges_from([(names[i], names[i+1]) for i in range(len(names)-1)])
        return graph