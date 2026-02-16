from networkx.classes import DiGraph
from zenlog import log
from dataclasses import dataclass, field
from mccode_antlr.instr import Instr, Instance
from mccode_antlr.instr.orientation import Orient
from mccode_antlr.common import Expr
from nexusformat.nexus import NXfield, NXgroup, NXcollection, NXinstrument
from typing import Union, Any


@dataclass
class NXInstr:
    instr: Instr
    declared: dict[str, Expr] = field(default_factory=dict)
    nxlog_root: str = field(default_factory=str)
    origin_name: Union[str, None] = None
    origin: Union[Orient, None] = None
    nx: Union[NXinstrument, None] = None
    only_nx: bool = field(default=False)
    forward_graph: Union[DiGraph, None] = None
    reverse_graph: Union[DiGraph, None] = None

    def __post_init__(self):
        """Start the C translation to ensure McCode-oddities are handled before any C-code parsing."""
        from mccode_antlr.common import ShapeType, DataType, Value
        from mccode_antlr import Flavor
        from mccode_antlr.translators.c import CTargetVisitor
        from mccode_antlr.translators.c_listener import CDeclarator
        from mccode_antlr.translators.c_listener import evaluate_c_defined_expressions
        config = dict(default_main=True, enable_trace=False, portable=False, include_runtime=True,
                      embed_instrument_file=False, verbose=False, output=None)
        translator = CTargetVisitor(self.instr, flavor=Flavor.MCSTAS, config=config)
        # translator.instrument_uservars is a list of `CDeclaration` objects, which are named tuples with
        # fields: name type init is_pointer is_array orig
        # translator.component_uservars is a dictionary of lists for each component type of `CDeclaration` objects.

        # only worry about instrument level variables for the moment, and convert the CDeclarations into Expr objects
        def c_declaration_to_expr(dec: CDeclarator) -> Expr:
            expr = Expr(Value(None)) if dec.init is None else Expr.parse(dec.init)
            expr.data_type = DataType.from_name(dec.dtype)
            if dec.is_pointer or dec.is_array:
                expr.shape_type = ShapeType.vector
            return expr

        variables = {dec.name: c_declaration_to_expr(dec) for dec in translator.instrument_uservars}

        # defined as
        # TODO this does not work because the simple "C"-style expression parser doesn't know about pointers
        # Hopefully any %include style lines have been removed at this point.
        all_inits = '\n'.join(init.source for init in self.instr.initialize)
        try:
            variables = evaluate_c_defined_expressions(variables, all_inits)
        except AttributeError:
            log.warn(f'Evaluating INITIALIZE %{{\n{all_inits}%}}\n failed; see preceding errors for hints why. '
                     'This is not an error condition (for now). Continuing')

        self.declared = variables
        #
        if self.origin is None:
            self.guess_origin()
            assert self.origin is not None
        if self.forward_graph is None:
            self.forward_graph = self.build_graph()
        if self.reverse_graph is None:
            self.reverse_graph = self.forward_graph.reverse(copy=True)
        #
        self.make_nx_instrument()

    def guess_origin(self):
        found = (
            (lambda x: self.origin_name == x.name)
            if self.origin_name is not None else
            (lambda x: 'samples' == x.type.category)
        )
        possible = [x for x in self.instr.components if found(x)]
        if not possible:
            msg = (
                '"sample" category components'
                if self.origin_name is None else
                f'component named {self.origin_name}'
            )
            log.warn(f'No {msg} in instrument, using ABSOLUTE positions')
        elif self.origin_name is not None and len(possible) > 1:
            log.error(
                f'{len(possible)} components named "{self.origin_name}"; using the first'
            )
        elif len(possible) > 1:
            log.warn(
                'More than one "sample" category component.'
                f' Using "{possible[0].name}" for origin name'
            )
        if possible:
            self.origin_name = possible[0].name
            self.origin = possible[0].orientation
        else:
            self.origin = Orient()

    def build_graph(self):
        graph = DiGraph()
        names = [x.name for x in self.instr.components]
        graph.add_nodes_from(names)
        # Default McCode instruments are linear
        graph.add_edges_from([(names[i], names[i+1]) for i in range(len(names)-1)])
        return graph

    def inputs(self, name):
        """Return the other end of edges ending at the named node"""
        return list(self.reverse_graph[name])

    def outputs(self, name):
        """Return the other end of edges starting at the named node"""
        return list(self.forward_graph[name])

    def make_transformations(self, inst: Instance):
        from mccode_antlr.instr.orientation import Vector, Angles, Parts
        from .orientation import NXOrient, NXParts

        def abs_ref(ref):
            return f'/entry/instrument/{ref}'

        def last_ref(refs: list[tuple[str, NXfield]]) -> str | None:
            try:
                return next(reversed(refs))[0]
            except StopIteration:
                pass

        at_vec, at_rel = inst.at_relative
        rot_vec, rot_rel = inst.rotate_relative

        any_abs = at_rel is None or rot_rel is None
        nx_ori = NXOrient(self, inst.orientation - self.origin) if any_abs else None
        if at_rel is None and rot_rel is None:
            return nx_ori.transformations(inst.name)

        trans = []
        if any_abs or at_rel != rot_rel:
            import warnings
            warnings.warn(
                "All mixed-reference-type orientations untested."
                "Only 'AT (x, y, z) ABSOLUTE ROTATE (a, b, c) REF' might work"
            )
        at_vec = Vector(*at_vec) if isinstance(at_vec, tuple) else at_vec
        rot_vec = Angles(*rot_vec) if isinstance(rot_vec, tuple) else rot_vec
        if at_rel is None:
            # Absolute position with relative rotation
            trans.extend(nx_ori.position_transformations(inst.name))
            # Get the _rotation_ of the reference to add here before any new rotation
            rel_ori = NXOrient(self, rot_rel.orientation - self.origin)
            trans.extend(rel_ori.rotation_transformations(rot_rel.name, last_ref(trans)))
            # Add the relative rotation onto the reference rotation
            rot = Parts(Parts.from_at_rotated(Vector(), rot_vec, True).stack()).reduce()
            nx_parts = NXParts(self, rot, rot)
            trans.extend(nx_parts.rotation_transformations(inst.name, last_ref(trans)))
        elif rot_rel is None:
            raise RuntimeError(
                "'AT (x, y, z) RELATIVE comp ROTATE (a, b, c) ABSOLUTE'"
                " not yet implemented"
            )
        elif at_rel != rot_rel:
            raise RuntimeError(
                "'AT (x, y, z) RELATIVE comp1 ROTATE (a, b, c) RELATIVE comp2'"
                " not yet implemented"
            )
        else:
            at_parts = Parts.from_at_rotated(at_vec, Angles(), True)
            rot_parts = Parts.from_at_rotated(Vector(), rot_vec, True)
            nx_parts = NXParts(self, at_parts, rot_parts)
            # TODO replace the absolute reference to the component by an
            #      absolute reference to _its_ `depends_on` target
            target = abs_ref(at_rel.name)
            if (depends_on := self.nx.get(at_rel.name)) is not None:
                if (t := depends_on.get('depends_on')) is not None:
                    # the relative target has a dependency, so we chain off of that:
                    if isinstance(t, NXfield):
                        # TODO what if this isn't a string?
                        t = str(t)
                    if t.startswith('/'):
                        target = t
                    elif t == '.':
                        target = None
                    else:
                        target = f'{target}/{t}'
                else:
                    # the relative target exists but has no dependency, so is absolute
                    target = None
            else:
                raise RuntimeError('transformations defined out of order')
            trans.extend(nx_parts.transformations(inst.name, target))

        return {k: v for k, v in trans}

    # def make_nx_instances(self):
    #     from .instance import NXInstance
    #     nx_instances = {}
    #     for index, inst in enumerate(self.instr.components):
    #         transformations = self.make_transformations(inst)
    #         nx_inst = NXInstance(self, inst, index, transformations, only_nx=self.only_nx)
    #         # add input and outputs
    #         if len(inputs := self.inputs(inst.name)):
    #             nx_inst.nx.attrs['inputs'] = inputs
    #         if len(outputs := self.outputs(inst.name)):
    #             nx_inst.nx.attrs['outputs'] = outputs
    #         # store the nx instance
    #         nx_instances[inst.name] = nx_inst
    #     return nx_instances

    def make_nx_instrument(self):
        from .instance import NXInstance

        self.nx = NXinstrument()
        self.nx['name'] = NXfield(value=self.instr.name)
        self.nx['mcstas'] = self.to_nx()

        for index, inst in enumerate(self.instr.components):
            transformations = self.make_transformations(inst)
            nx_inst = NXInstance(self, inst, index, transformations, only_nx=self.only_nx)
            # add input and outputs
            if len(inputs := self.inputs(inst.name)):
                nx_inst.nx.attrs['inputs'] = inputs
            if len(outputs := self.outputs(inst.name)):
                nx_inst.nx.attrs['outputs'] = outputs
            # store the nx instance representation in NeXus
            self.nx[inst.name] = nx_inst.nx


    def to_nx(self):
        # quick and very dirty:
        return NXfield(str(self.instr))

    def expr2nx(self, expr: Union[str, Expr, Any]):
        """Intended to convert *Expr* objects to NeXus-representable objects"""
        # FIXME this is called to wrap and re-wrap the same data
        #       during translation of a component with properties. It may be worth
        #       separating the parameter and component functionality.
        from moreniius.utils import link_specifier, NotNXdict
        from nexusformat.nexus import NXlog
        if hasattr(expr, '_value') and isinstance(getattr(expr, '_value'), NotNXdict):
            # Avoid unwrapping the non-NX dictionary at this stage since it is
            # silently converted to a string-like thing which as an __iter__ property
            return expr
        if isinstance(expr, NXlog):
            # Do not decompose a value if we already wrapped it in NXlog
            return expr
        if not isinstance(expr, str) and hasattr(expr, '__iter__'):
            parts = [self.expr2nx(x) for x in expr]
            return tuple(parts) if isinstance(expr, tuple) else parts
        if not isinstance(expr, Expr):
            return expr

        if expr.is_constant:
            return expr.value

        evaluated = expr.evaluate(self.declared)
        if evaluated.is_constant:
            return evaluated.value

        dependencies = [par.name for par in self.instr.parameters if evaluated.depends_on(par.name)]
        if len(dependencies) == 1 and str(expr) == str(dependencies[0]):
            from moreniius.utils import linked_nxlog
            return linked_nxlog(f'{self.nxlog_root}/{dependencies[0]}')

        if len(dependencies):
            log.warn(f'The expression {expr} depends on instrument parameter(s) {dependencies}\n'
                     f'A link will be inserted for each; make sure their values are stored at {self.nxlog_root}/')
            links = {par: link_specifier(par, f'{self.nxlog_root}/{par}') for par in dependencies}
            return NXcollection(expression=str(expr), **links)

        return str(expr)

    def make_nx(self, nx_class, *args, **kwargs):
        from nexusformat.nexus import NXlog
        from moreniius.utils import NotNXdict
        nx_args = [self.expr2nx(expr) for expr in args]
        nx_kwargs = {name: self.expr2nx(expr) for name, expr in kwargs.items()}

        # logged parameters are sometimes requested as NXfields, but should be NXlogs
        want_log = nx_class == NXfield and len(nx_args) == 1
        nx_arg = nx_args[0] if want_log else None
        if want_log and isinstance(nx_arg, NXlog):
            # The NXlog returned by expr2nx doesn't have the needed attributes:
            for k, v in nx_kwargs.items():
                nx_arg.attrs[k] = v
            return nx_arg
        # Hopefully less often, a collection of links in an NXcollection
        if want_log and isinstance(nx_arg, NXcollection) and 'expression' in nx_arg:
            not_expr = [x for x in nx_arg if x != 'expression']
            if len(not_expr) == 1:
                arg = nx_arg[not_expr[0]]
                if isinstance(arg, NXfield):
                    # if this is a link, we should not add any attributes
                    # since the filewriter will ignore them
                    if hasattr(arg, '_value') and isinstance(d:=getattr(arg, '_value'), NotNXdict) and d.get('module', '') == 'link':
                        return arg
                    # We have and want an NXfield, but it might be missing attributes specified in the nx_kwargs
                    # Passing the keywords to the NXfield constructor versus this method is not identical,
                    # since some keyword arguments are reserved (and only some of which are noted)
                    #   Explicit keywords, used in the constructor:
                    #       value, name, shape, dtype, group, attrs
                    #   Keywords extracted from the kwargs dict, if present (and all controlling HDF5 file attributes?):
                    #       chunks, compression, compression_opts, fillvalue, fletcher32, maxshape, scaleoffset, shuffle
                    # For now, just assume all keywords provided here are _actually_ attributes for the NXfield
                    # which is an extension of a dict, but can *not* use the update method, since the __setitem__
                    # method is overridden to wrap inputs in NXattr objects :/
                    for k, v in nx_kwargs.items():
                        arg.attrs[k] = v
                    return arg

                # TODO make this return an nx_class once we're sure that nx_kwargs is parseable (no mccode_antlr.Expr)
                if all(x in arg for x in ('module', 'config')):
                    # This is a file-writer stream directive? So make a group
                    grp = NXgroup(entries={not_expr[0]: arg})
                    for attr, val in nx_kwargs.items():
                        grp.attrs[attr] = val
                    return grp
                print('!!')
                print(arg)
                return nx_class(arg, **nx_kwargs)
            else:
                raise RuntimeError('Not sure what I should do here')
        return nx_class(*nx_args, **nx_kwargs)
