
def make_motorized_instrument():
    from mccode_antlr.assembler import Assembler
    from mccode_antlr.reader import MCSTAS_REGISTRY, LocalRegistry
    from mccode_to_kafka.writer import da00_dataarray_config, da00_variable_config

    inst = Assembler('inst', registries=[MCSTAS_REGISTRY])
    inst.parameter('double ex/"m"=0')
    inst.parameter('double phi/"degree"=0')

    inst.component('origin', 'Arm', at=(0, 0, 0))
    inst.component('source', 'Source_simple', at=[(0, 0, 0), 'origin'])
    inst.component('xpos', 'Arm', at=[('ex', 0, 0), 'source'])
    inst.component('zrot', 'Arm', at=[(0, 0, 0), 'xpos'], rotate=[(0, 0, 'phi'), 'xpos'])

    return inst.instrument


def test_motorized_instrument():
    import moreniius
    motorized = make_motorized_instrument()
    nx = moreniius.MorEniius.from_mccode(motorized, origin='origin', only_nx=False, absolute_depends_on=True)
    assert nx is not None
    #TODO add actual tests for the contents of, e.g., the dumped NeXus Structure