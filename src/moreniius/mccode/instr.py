from zenlog import log
from dataclasses import dataclass, field
from mccode_antlr.instr import Instr
from mccode_antlr.common import Expr
from nexusformat.nexus import NXfield, NXcollection


@dataclass
class NXInstr:
    instr: Instr
    declared: dict[str, Expr] = field(default_factory=dict)
    nxlog_root: str = field(default_factory=str)

    def __post_init__(self):
        """Start the C translation to ensure McCode-oddities are handled before any C-code parsing."""
        from mccode_antlr.common import ShapeType, DataType, Value
        from mccode_antlr.translators.target import MCSTAS_GENERATOR
        from mccode_antlr.translators.c import CTargetVisitor, CDeclaration
        from mccode_antlr.translators.c_listener import evaluate_c_defined_expressions
        config = dict(default_main=True, enable_trace=False, portable=False, include_runtime=True,
                      embed_instrument_file=False, verbose=False, output=None)
        translator = CTargetVisitor(self.instr, generate=MCSTAS_GENERATOR, config=config)
        # translator.instrument_uservars is a list of `CDeclaration` objects, which are named tuples with
        # fields: name type init is_pointer is_array orig
        # translator.component_uservars is a dictionary of lists for each component type of `CDeclaration` objects.

        # only worry about instrument level variables for the moment, and convert the CDeclarations into Expr objects
        def c_declaration_to_expr(dec: CDeclaration) -> Expr:
            expr = Expr(Value(None)) if dec.init is None else Expr.parse(dec.init)
            expr.data_type = DataType.from_name(dec.type)
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

    def expr2nx(self, expr: Expr):
        from moreniius.utils import link_specifier
        if isinstance(expr, list):
            return [self.expr2nx(x) for x in expr]
        if isinstance(expr, tuple):
            return tuple([self.expr2nx(x) for x in expr])
        if not isinstance(expr, Expr):
            return expr

        if expr.is_constant:
            return expr.value

        evaluated = expr.evaluate(self.declared)
        if evaluated.is_constant:
            return evaluated.value

        dependencies = [par.name for par in self.instr.parameters if evaluated.depends_on(par.name)]
        if len(dependencies):
            log.warn(f'The expression {expr} depends on instrument parameter(s) {dependencies}\n'
                     f'A link will be inserted for each; make sure their values are stored at {self.nxlog_root}/')
            links = {par: link_specifier(par, f'{self.nxlog_root}/{par}') for par in dependencies}
            return NXcollection(expression=str(expr), **links)

        return str(expr)

    def make_nx(self, nx_class, *args, **kwargs):
        nx_args = [self.expr2nx(expr) for expr in args]
        nx_kwargs = {name: self.expr2nx(expr) for name, expr in kwargs.items()}
        return nx_class(*nx_args, **nx_kwargs)
