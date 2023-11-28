from __future__ import annotations
from mccode_antlr.instr import Instr


class MorEniius:
    def __init__(self, nx, only_nx: bool = False, absolute_depends_on: bool = False):
        self.nx = nx
        self.only_nx = only_nx
        self.absolute_depends_on = absolute_depends_on

    @classmethod
    def from_mccode(cls, instr: Instr,
                    origin: str | None = None,
                    only_nx: bool = False,
                    nxlog_root: str | None = None,
                    absolute_depends_on: bool = False
                    ):
        from nexusformat.nexus import NXfield
        from .mccode import NXMcCode, NXInstr
        nxlog_root = nxlog_root or ''
        nx_mccode = NXMcCode(NXInstr(instr, nxlog_root=nxlog_root), origin_name=origin)
        nxs_obj = nx_mccode.instrument(only_nx=only_nx)
        nxs_obj['name'] = NXfield(value=instr.name)
        return cls(nxs_obj, only_nx=only_nx, absolute_depends_on=absolute_depends_on)

    def to_nexus_structure(self):
        from .writer import Writer
        return Writer(self.nx).to_nexus_structure(only_nx=self.only_nx, absolute_depends_on=self.absolute_depends_on)

    def to_json(self, filename, indent=4):
        from .writer import Writer
        if not filename.endswith('.json'):
            filename += '.json'
        Writer(self.nx).to_json(filename, indent=indent, only_nx=self.only_nx, absolute_depends_on=self.absolute_depends_on)
