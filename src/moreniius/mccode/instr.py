from zenlog import log
from dataclasses import dataclass, field
from mccode_antlr.instr import Instr
from mccode_antlr.common import Expr
from nexusformat.nexus import NXfield, NXgroup, NXcollection
from typing import Union, Any


@dataclass
class NXInstr:
    instr: Instr
    declared: dict[str, Expr] = field(default_factory=dict)
    nxlog_root: str = field(default_factory=str)

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
