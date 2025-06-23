
def make_motorized_instrument():
    from mccode_antlr import Flavor
    from mccode_antlr.assembler import Assembler

    inst = Assembler('inst', flavor=Flavor.MCSTAS)
    inst.parameter('double ex/"m"=0')
    inst.parameter('double phi/"degree"=0')

    inst.component('origin', 'Arm', at=(0, 0, 0))
    inst.component('source', 'Source_simple', at=[(0, 0, 0), 'origin'])
    inst.component('xpos', 'Arm', at=[('ex', 0, 0), 'source'])
    inst.component('zrot', 'Arm', at=[(0, 0, 0), 'xpos'], rotate=[(0, 0, 'phi'), 'xpos'])
    inst.component('aposrot', 'Arm', at=(1, 2, 3), rotate=(45, 55, 60))

    return inst.instrument


def test_motorized_instrument():
    import moreniius
    motorized = make_motorized_instrument()
    nx = moreniius.MorEniius.from_mccode(motorized, origin='origin', only_nx=False, absolute_depends_on=True)
    assert nx is not None
    #TODO add actual tests for the contents of, e.g., the dumped NeXus Structure
    ns = nx.to_nexus_structure()

    expected = {
        'entry': {
            'type': 'group',
            'children': 1,
            'next': 0,
            'attributes': [{'name': 'NX_class', 'dtype': 'string', 'values': 'NXentry'}]
        },
        'instrument': {
            'type': 'group',
            'children': 7,
            'next': 0,
            'attributes': [{'name': 'NX_class', 'dtype': 'string', 'values': 'NXinstrument'}]
        },
    }
    for name, has in expected.items():
        assert 'children' in ns
        assert len(ns['children']) >= has['next']
        ns = ns['children'][has['next']]
        assert all(x in ns for x in ('type', 'name', 'children', 'attributes'))
        assert ns['name'] == name
        assert ns['attributes'] == has['attributes']
        assert len(ns['children']) == has['children']

    xpos = ns['children'][3]
    zrot = ns['children'][4]
    aposrot = ns['children'][5]


    from json import dumps

    for cns in (xpos, zrot, aposrot):
        assert 'children' in cns
        assert 'transformations' in [c['name'] for c in cns['children'] if 'name' in c]
        t = [c for c in cns['children'] if 'name' in c and c['name'] == 'transformations'][0]
        assert 'children' in t
        t = t['children']
        for c in t:
            # Each child can _either_ be a dataset, with 'module' at its top level
            # Or a group, with 'name', etc. at its top level

            if 'module' in c:
                # this transformation is static, and a dataset
                assert 'dataset' == c['module']
                assert all(x in c for x in ('config', 'attributes'))
                assert all(x in c['config'] for x in ('name', 'values', 'type'))
                attrs = c['attributes']
                assert len(attrs) == 4
                assert all(all(x in a for x in ('name', 'values', 'dtype')) for a in attrs)
                assert all(a['name'] in ('vector', 'depends_on', 'transformation_type', 'units') for a in attrs)
            else:
                # this transformation is dynamic and a group
                assert all(x in c for x in ('name', 'type', 'children', 'attributes'))
                assert 'group' == c['type']
                attrs = c['attributes']
                assert len(attrs) == 1
                attr = attrs[0]
                assert all(x in attr for x in ('name', 'dtype', 'values'))
                assert 'NX_class' == attr['name']
                assert 'NXgroup' == attr['values']

                # The children should contain a link to the log ... is the order important?
                # Must the number of children always be the same?
                assert all('module' in cc for cc in c['children'])
                assert sum('link' == cc['module'] for cc in c['children']) <= 1
                for cc in c['children']:
                    if 'link' == cc['module']:
                        assert all(x in cc['config'] for x in ('name', 'source'))
                    else:
                        assert all(x in cc['config'] for x in ('name', 'values', 'type'))
                        assert cc['config']['name'] in ('vector', 'depends_on', 'transformation_type', 'units')

    # for name, has in expected.items():
    #     print({x : list(ns[x]) for x in ns})
    #     assert all(x in ns for x in has)
    #     assert len(ns['children']) == 1
    #     assert ns['name'] == name
    #     ns = ns['children'][0]

    #
    # instr = ns['entry']['instrument']
    # #
    # print(dumps(xpos, indent=2))
    # print(dumps(zrot, indent=1))
    # print(dumps(aposrot, indent=1))