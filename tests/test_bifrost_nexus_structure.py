
def get_bifrost_instr():
    from mccode_antlr.io.json import load_json
    from pathlib import Path
    file = Path(__file__).parent / 'bifrost.instr.json'
    return load_json(file)

def test_bifrost_nexus_structure():
    # from pathlib import Path
    # from json import dump
    from moreniius import MorEniius
    instr = get_bifrost_instr()
    me = MorEniius.from_mccode(instr, origin='sample_origin', only_nx=False, absolute_depends_on=False)
    ns = me.to_nexus_structure()

    # jq path to pulse_shaping_chopper_1's rotation_speed
    #.children[0].children[0].children[12].children[2]
    obj = ns['children'][0]['children'][0]['children'][12]['children'][2]


    assert 'type' in obj
    assert obj['type'] == 'group'
    children = obj['children']
    for child in children:
        assert 'module' in child
        assert 'config' in child
        assert child['module'] == 'link'
        assert all(x in child['config'] for x in ('name', 'source'))
        assert child['config']['name'] == child['config']['source'].split('/')[-1]

    # The channel-5 arm is oriented 0-degrees rotated from the tank rotation angle
    # and _should_ be a NXccordinate_system directly dependent on that NXlog'ed value
    # jless finds it at .children[0].children[0].children[255]
    arm = ns['children'][0]['children'][0]['children'][255]
    assert 'type' in arm
    assert arm['type'] == 'group'
    assert 'name' in arm
    assert arm['name'] == 'channel_5_arm'

    assert 'attributes' in arm
    class_name = None
    for attribute in arm['attributes']:
        if (n := attribute.get('name')) is not None and n == 'NX_class':
            class_name = attribute['values']
    assert class_name == 'NXcoordinate_system'

    assert 'children' in arm
    for child in arm['children']:
        if (m := child.get('module')) is not None and m == 'dataset':
            assert 'config' in child
            if (n := child['config'].get('name')) is not None and n == 'depends_on':
                # Check for the actual named group?
                assert child['config']['values'].startswith('/')
