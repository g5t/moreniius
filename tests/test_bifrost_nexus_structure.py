
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

    json_file = Path(__file__).parent / 'bifrost_nexus_structure.json'
    with open(json_file, 'w') as f:
        dump(ns, f)

    # jq path to _wrong_ pulse_shaping_chopper_1's rotation_speed value
    # .children[0].children[0].children[11].children[2].config.values[0]
    # so the full object is
    obj = ns['children'][0]['children'][0]['children'][11]['children'][2]
    assert 'module' in obj
    assert 'config' in obj
    if obj['module'] == 'dataset':
        print('This module should be a link!')
    assert obj['module'] == 'link'

    assert json_file.exists()