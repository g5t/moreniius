
def get_bifrost_instr():
    from mccode_antlr.io.json import load_json
    from pathlib import Path
    file = Path(__file__).parent / 'bifrost.instr.json'
    return load_json(file)

def test_bifrost_nexus_structure():
    from moreniius import MorEniius, NexusStructureNavigator
    
    instr = get_bifrost_instr()
    me = MorEniius.from_mccode(instr, origin='sample_origin', only_nx=False, absolute_depends_on=False)
    ns_dict = me.to_nexus_structure()
    
    # Use navigator for cleaner access
    nav = NexusStructureNavigator(ns_dict)

    # Old path: .children[0].children[0].children[12].children[2]
    # Navigate to pulse_shaping_chopper_1's rotation_speed
    entry = nav['entry']
    instrument = entry['instrument']
    
    # Get child #12 (pulse_shaping_chopper_1) and its child #2 (rotation_speed)
    # Since we don't know the exact name, fall back to index access for this specific case
    pulse_chopper = instrument.structure['children'][12]
    obj = pulse_chopper['children'][2]

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
    # and _should_ be a NXcoordinate_system directly dependent on that NXlog'ed value
    # Old path: .children[0].children[0].children[255]
    arm_dict = instrument.structure['children'][255]
    assert 'type' in arm_dict
    assert arm_dict['type'] == 'group'
    assert 'name' in arm_dict
    assert arm_dict['name'] == 'channel_5_arm'
    
    # Could also access by name if it's unique
    channel_5_arm = nav['entry']['instrument']['channel_5_arm']
    assert channel_5_arm.structure['name'] == 'channel_5_arm'

    # Check attributes using navigator
    nx_class_attr = channel_5_arm['@NX_class']
    assert nx_class_attr['values'] == 'NXcoordinate_system'

    # Check children for depends_on
    assert 'children' in channel_5_arm.structure
    for child in channel_5_arm.structure['children']:
        if (m := child.get('module')) is not None and m == 'dataset':
            assert 'config' in child
            if (n := child['config'].get('name')) is not None and n == 'depends_on':
                # Check for the actual named group?
                assert child['config']['values'].startswith('/')
