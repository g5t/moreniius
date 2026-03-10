from moreniius import NexusStructureNavigator


def build_bifrost_instr():
    from mccode_antlr import Flavor
    from mccode_antlr.assembler import Assembler
    from niess.bifrost.parameters import primary_parameters, tank_parameters
    from niess.bifrost import Tank, Primary

    primary = Primary.from_calibration(primary_parameters())
    tank = Tank.from_calibration(tank_parameters())

    bifrost = Assembler('bifrost', flavor=Flavor.MCSTAS)
    primary.to_mccode(bifrost)
    tank.to_mccode(bifrost, 'sample_origin')

    return bifrost.instrument


def get_bifrost_instr():
    from mccode_antlr.io.json import load_json, save_json
    from pathlib import Path
    file = Path(__file__).parent / 'bifrost.instr.json'
    try:
        instr = load_json(file)
    except:
        instr = build_bifrost_instr()
        save_json(instr, file)
    return instr

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


    # arm_dict = nav['entry']['instrument']['channel_5_arm'].structure
    # assert 'type' in arm_dict
    # assert arm_dict['type'] == 'group'
    # assert 'name' in arm_dict
    # assert arm_dict['name'] == 'channel_5_arm'
    
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


def is_typed_dataset(obj, typ):
    if 'module' not in obj or obj['module'] is None or obj['module'] != 'dataset':
        return False
    if 'config' not in obj or obj['config'] is None or 'values' not in obj['config']:
        return False
    return isinstance(obj['config']['values'], typ)

def is_typed_array_dataset(obj, typ, shape: list[int]):
    """
    Check if a NeXus Structure JSON object is a static dataset
    representing an array of the specified type and shape.

    Parameters
    ----------
    obj : dict
        The JSON object resulting from, e.g., the Navigator's getitem instance
    typ: typename
        The type of the dataset to check
    shape: list[int]
        The shape of the dataset to check -- C-ordered, [innermost, ..., outermost]
        Any dimension with 'expected' length -1 will match automatically
    """
    if not is_typed_dataset(obj, list):
        return False
    values = obj['config']['values']
    sh = []
    while hasattr(values, '__len__'):
        sh.append(len(values))
        values = values[0]
    if not isinstance(values, typ):
        return False
    found_shape = list(reversed(sh))
    if not len(found_shape) == len(shape):
        return False
    for i, n in enumerate(found_shape):
        if shape[i] == -1:
            shape[i] = n

    return found_shape == shape


def is_nxlog_group(loc):
    """
    Check if a NeXus Structure JSON object Navigator location is a NXlog group

    Parameters
    loc: NavigatorStructureNavigator
        A navigated-to location that should be an NXlog group
    """
    from moreniius import NexusStructureNavigator
    if not isinstance(loc, NexusStructureNavigator):
        return False
    if 'type' not in loc.structure or loc.structure['type'] != 'group':
        return False
    return loc['@NX_class']['values'] == 'NXlog'


def test_bifrost_choppers_have_necessary_parameters():
    from moreniius import MorEniius, NexusStructureNavigator

    instr = get_bifrost_instr()
    me = MorEniius.from_mccode(instr, origin='sample_origin', only_nx=False,
                               absolute_depends_on=False)
    ns_dict = me.to_nexus_structure()

    # Use navigator for cleaner access
    nav = NexusStructureNavigator(ns_dict)

    choppers = (
        'pulse_shaping_chopper_1', 'pulse_shaping_chopper_2',
        'frame_overlap_chopper_1', 'frame_overlap_chopper_2',
        'bandwidth_chopper_1', 'bandwidth_chopper_2',
    )
    for name in choppers:
        chopper = nav['entry/instrument'][name]
        assert chopper.structure['type'] == 'group'
        assert chopper['@NX_class']['values'] == 'NXdisk_chopper'

        # Every chopper needs to have static datasets:
        for prop, typ in (('slits', int), ('radius', float), ('slit_angle', float), ('slit_height', float)):
            assert is_typed_dataset(chopper[prop], typ)
        # the slit angles should be an even number of values (or always 2 for BIFROST)
        assert is_typed_array_dataset(chopper['slit_edges'], float, [2])

        # And the speed and phase (for McStas simulations) should be NXlogs
        for prop in ('rotation_speed', 'phase'):
            assert is_nxlog_group(chopper[prop])

    guides = (
        'nboa', #TODO: insert more guides here
    )
    for name in guides:
        guide = nav['entry/instrument'][name]
        assert guide.structure['type'] == 'group'
        assert guide['@NX_class']['values'] == 'NXguide'

        # TODO: (Maybe?) The NXguide constructed thus far does not include any m values
        # for prop, typ in (('m', float),):
        #     assert is_typed_dataset(guide[prop], typ) # this should be an array?

        geometry = guide['OFF_GEOMETRY']
        assert geometry.structure['type'] == 'group'
        assert geometry['@NX_class']['values'] == 'NXoff_geometry'
        assert is_typed_array_dataset(geometry['vertices'], float, [3, -1])
        assert is_typed_array_dataset(geometry['winding_order'], int, [-1])
        assert is_typed_array_dataset(geometry['faces'], int, [-1])

        vertices = geometry['vertices']['config']['values']
        winding = geometry['winding_order']['config']['values']
        faces = geometry['faces']['config']['values']

        assert 0 <= min(winding) and max(winding) < len(vertices)
        assert 0 <= min(faces) and max(faces) < len(winding)

        # If the second moment of the vertices is non-zero, the shape likely has volume
        x_avg, y_avg, z_avg = 0, 0, 0
        for x, y, z in vertices:
            x_avg += x
            y_avg += y
            z_avg += z
        x_avg /= len(vertices)
        y_avg /= len(vertices)
        z_avg /= len(vertices)

        x_sec, y_sec, z_sec = 0, 0, 0
        for x, y, z in vertices:
            x_sec += (x - x_avg)**2
            y_sec += (y - y_avg)**2
            z_sec += (z - z_avg)**2
        x_sec /= len(vertices)
        y_sec /= len(vertices)
        z_sec /= len(vertices)
        assert x_sec > 0
        assert y_sec > 0
        assert z_sec > 0


