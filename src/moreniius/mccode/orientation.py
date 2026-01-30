from __future__ import annotations

from zenlog import log
from dataclasses import dataclass, field
from mccode_antlr.instr import Orient, Parts, Part
from nexusformat.nexus import NXfield
from .instr import NXInstr

@dataclass
class NXPart:
    instr: NXInstr
    o: Part

    def expr2nx(self, expr):
        return self.instr.expr2nx(expr)

    def make_nx(self, nx_class, *args, **kwargs):
        return self.instr.make_nx(nx_class, *args, **kwargs)

    def make_translation(self, norm, vec, dep):
        # if `norm` is a link or NXlog, we should make a group not an NXfield
        return self.make_nx(NXfield, norm, vector=vec, depends_on=dep, transformation_type='translation', units='m')

    def translations(self, dep: str, name: str) -> list[tuple[str, NXfield]]:
        from mccode_antlr.instr import RotationPart
        from mccode_antlr.common import Expr, Value
        if isinstance(self.o, RotationPart):
            raise RuntimeError('Part is a rotation!')
        pos = self.o.position()
        if any(isinstance(c, (Expr, Value)) for c in (pos.x, pos.y, pos.z)):
            translations = []
            for n, c, v in (('x', pos.x, [1, 0, 0]), ('y', pos.y, [0, 1, 0]), ('z', pos.z, [0, 0, 1])):
                if c != Expr.parse('0'):
                    next_name = f'{name}_{n}'
                    translations.append((next_name, self.make_translation(c, v, dep)))
                    dep = next_name
            return translations
        # vector is all constants, hopefully
        norm = pos.length()
        vec = pos if norm.is_zero else pos/norm
        return [(name, self.make_translation(norm, vec, dep))]

    def rotation(self, dep: str) -> NXfield:
        from mccode_antlr.instr import TranslationPart
        if isinstance(self.o, TranslationPart):
            raise RuntimeError('Part is a translation')
        try:
            axis, angle, angle_unit = self.o.rotation_axis_angle
        except RuntimeError as error:
            log.error(f'Failed to get rotation axis and angle: {error}')
            print(repr(self.o))
            raise NotImplementedError()

        # handle the case where angle is not a constant?
        return self.make_nx(NXfield, angle, vector=axis, depends_on=dep, transformation_type='rotation', units=angle_unit)

    def transformations(self, name: str, dep: str | None = None) -> list[tuple[str, NXfield]]:
        if self.o.is_translation and self.o.is_rotation:
            ops = self.translations(dep, name)
            rot = self.rotation(ops[-1][0])
            return [*ops, (f'{name}_r', rot)]
        elif self.o.is_translation:
            return self.translations(dep, name)
        elif self.o.is_rotation:
            return [(name, self.rotation(dep))]
        else:
            return []


@dataclass
class NXParts:
    instr: NXInstr
    position: Parts
    rotation: Parts

    def _transformations(self, name: str, dep: str, typ: str, stack):
        nx_transformations = []
        for i, op in enumerate(stack):
            parts = NXPart(self.instr, op).transformations(f'{name}_{typ}{i}', dep)
            nx_transformations.extend(parts)
            if len(parts) and len(parts[-1]):
                dep = parts[-1][0]
        return nx_transformations

    def position_transformations(self, name: str, dep: str | None = None ) -> list[tuple[str, NXfield]]:
        dep = dep or '.'
        return self._transformations(name, dep, 't', self.position.stack())

    def rotation_transformations(self, name: str, dep: str | None = None) -> list[tuple[str, NXfield]]:
        dep = dep or '.'
        return self._transformations(name, dep, 'r', self.rotation.stack())

    def transformations(self, name: str, dep: str | None = None) -> list[tuple[str, NXfield]]:
        parts = self.position_transformations(name, dep=dep)
        dep = parts[-1][0] if len(parts) and len(parts[-1]) else None
        return parts + self.rotation_transformations(name, dep=dep)


@dataclass
class NXOrient:
    instr: NXInstr
    do: Orient
    nx_parts: NXParts | None = None

    def __post_init__(self):
        # collapse all possible chained orientation information
        # But keep the rotations and translations separate
        pos, rot = self.do.position_parts(), self.do.rotation_parts()
        # make an ordered list of the requisite NXfield entries
        self.nx_parts = NXParts(self.instr, pos, rot)

    def transformations(self, name: str) -> dict[str, NXfield]:
        # make an ordered list of the requisite NXfield entries, and turn it into a dict
        return {k: v for k, v in self.nx_parts.transformations(name)}

    def position_transformations(self, name: str, dep: str | None = None) -> list[tuple[str, NXfield]]:
        return self.nx_parts.position_transformations(name, dep)

    def rotation_transformations(self, name: str, dep: str | None = None) -> list[tuple[str, NXfield]]:
        return self.nx_parts.rotation_transformations(name, dep)


