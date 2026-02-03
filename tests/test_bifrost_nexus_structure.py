
def get_bifrost_instr():
    from mccode_antlr.io.json import load_json
    from pathlib import Path
    file = Path(__file__).parent / 'bifrost.instr.json'
    return load_json(file)

def test_bifrost_nexus_structure():
    from pathlib import Path
    from json import dump
    from moreniius import MorEniius
    instr = get_bifrost_instr()
    me = MorEniius.from_mccode(instr, origin='sample_origin', only_nx=False, absolute_depends_on=False)
    ns = me.to_nexus_structure()

    # jq path to _wrong_ pulse_shaping_chopper_1's rotation_speed value
    # .children[0].children[0].children[11].children[2].config.values[0]
    # so the full object is
    obj = ns['children'][0]['children'][0]['children'][11]['children'][2]

    assert 'type' in obj
    assert obj['type'] == 'group'
    children = obj['children']
    for child in children:
        assert 'module' in child
        assert 'config' in child
        assert child['module'] == 'link'
        assert all(x in child['config'] for x in ('name', 'source'))
        assert child['config']['name'] == child['config']['source'].split('/')[-1]
