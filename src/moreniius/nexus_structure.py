#!/usr/bin/env python
# coding: utf-8

from __future__ import annotations
from pathlib import Path
from mccode_antlr.instr import Instr


def load_instr(filepath: str | Path) -> Instr:
    """Loads an Instr object from a .instr file or a HDF5 file"""
    from mccode_antlr.loader import load_mcstas_instr
    from mccode_antlr.io import load_hdf5

    if not isinstance(filepath, Path):
        filepath = Path(filepath)
    if not filepath.exists() or not filepath.is_file():
        raise ValueError('The provided filepath does not exist or is not a file')

    if filepath.suffix == '.instr':
        return load_mcstas_instr(filepath)

    return load_hdf5(filepath)


def to_nexus_structure(instr: Instr) -> dict:
    from moreniius import additions
    from moreniius import MorEniius
    nx = MorEniius.from_mccode(instr, origin='sample_stack', only_nx=False, absolute_depends_on=True)
    return nx.to_nexus_structure()


def convert():
    """Convert an Instr (HDF5) or .instr (text) file to an equivalent NeXus Structure JSON string"""
    import argparse
    parser = argparse.ArgumentParser(description='Convert an Instr (HDF5) or .instr (text) file to an equivalent NeXus Structure JSON string')
    parser.add_argument('filename', type=str, help='the file to convert')
    parser.add_argument('--format', type=str, default='json', help='the output format, either json or pickle')
    args = parser.parse_args()
    instr = load_instr(args.filename)
    structure = to_nexus_structure(instr)
    if args.format == 'json':
        from json import dumps
        print(dumps(structure))
    else:
        raise RuntimeError(f"Unknown format {args.format}")


if __name__ == '__main__':
    convert()
