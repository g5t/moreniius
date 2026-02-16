
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


def json_is_nxobj(obj: dict, nxtype: str):
    if 'type' not in obj or obj['type'] != 'group':
        return False
    if 'attributes' not in obj:
        return False
    for a in obj['attributes']:
        if a['name'] == 'NX_class' and a['values'] == nxtype:
            return True
    return False


def json_is_nxlog(obj: dict):
    return json_is_nxobj(obj, 'NXlog')


def get_nxlog_link_count():
    from moreniius.utils import nxlog_data_links
    return len(nxlog_data_links('fake'))


def test_motorized_instrument():
    import moreniius
    from moreniius import NexusStructureNavigator
    
    motorized = make_motorized_instrument()
    nx = moreniius.MorEniius.from_mccode(motorized, origin='origin', only_nx=False, absolute_depends_on=True)
    assert nx is not None
    
    ns_dict = nx.to_nexus_structure()
    nav = NexusStructureNavigator(ns_dict)

    # Check entry level
    entry = nav['entry']
    assert entry.structure['name'] == 'entry'
    assert entry.structure['type'] == 'group'
    assert len(entry.structure['children']) == 1
    
    entry_nx_class = entry['@NX_class']
    assert entry_nx_class == {'name': 'NX_class', 'dtype': 'string', 'values': 'NXentry'}

    # Check instrument level
    instrument = nav['entry']['instrument']
    assert instrument.structure['name'] == 'instrument'
    assert instrument.structure['type'] == 'group'
    assert len(instrument.structure['children']) == 7
    
    instrument_nx_class = instrument['@NX_class']
    assert instrument_nx_class == {'name': 'NX_class', 'dtype': 'string', 'values': 'NXinstrument'}

    # Access components directly by name using navigator
    xpos = nav['entry']['instrument']['xpos']
    zrot = nav['entry']['instrument']['zrot']
    aposrot = nav['entry']['instrument']['aposrot']

    # deps = {
    #     'xpos_t0_x': ('/entry/instrument/source', [1, 0, 0], 'translation'),
    #     # 'zrot_t0_x': ('/entry/instrument/xpos', [1, 0, 0], 'translation'), # the empty translation is skipped
    #     'zrot_r0': ('/entry/instrument/xpos', [0, 0, 1], 'rotation'), # so the rotation depends directly on xpos
    # }

    # /entry/instrumen/source is placed absolutely, so xpos_t0_x's dependency on it
    # becomes absolute as well.
    # zrot_r0 depends on xpos, but we look into its transformations group
    deps = {
        'xpos_t0_x': ('.', [1, 0, 0], 'translation'),
        'zrot_r0': ('/entry/instrument/xpos/transformations/xpos_t0_x', [0, 0, 1], 'rotation'),
    }

    for cns_nav in (xpos, zrot, aposrot):
        cns = cns_nav.structure
        assert 'children' in cns
        assert 'transformations' in [c['name'] for c in cns['children'] if 'name' in c]
        t = [c for c in cns['children'] if 'name' in c and c['name'] == 'transformations'][0]
        assert 'children' in t
        t = t['children']
        for c in t:
            # Each child can _either_ be a dataset, with 'module' at its top level
            # Or a group, with 'name', etc. at its top level

            if 'module' in c and 'dataset' == c['module']:
                # this transformation is static, and a dataset
                assert 'dataset' == c['module']
                assert all(x in c for x in ('config', 'attributes'))
                assert all(x in c['config'] for x in ('name', 'values', 'type'))
                attrs = c['attributes']
                assert len(attrs) == 4
                assert all(all(x in a for x in ('name', 'values', 'dtype')) for a in attrs)
                assert all(a['name'] in ('vector', 'depends_on', 'transformation_type', 'units') for a in attrs)
            elif 'module' in c and 'link' == c['module']:
                assert 'config' in c
                assert all(x in c['config'] for x in ('name', 'source'))
            elif json_is_nxlog(c):
                attrs = c['attributes']
                assert len(attrs) == 5

                dep = deps[c['name']]
                d = {
                    'depends_on': dep[0],
                    'vector': dep[1],
                    'transformation_type': dep[2],
                    'units': 'm' if dep[2] == 'translation' else 'degrees',
                }
                for k, v in d.items():
                    assert sum(a['name'] == k for a in attrs) == 1
                    attr = next(a for a in attrs if a['name'] == k)
                    assert attr['values'] == v

                # The children should contain a links to the log datasets
                # ... is the order important?
                assert all('module' in cc for cc in c['children'])

                assert sum('link' == cc['module'] for cc in c['children']) == get_nxlog_link_count()
                for cc in c['children']:
                    if 'link' == cc['module']:
                        assert all(x in cc['config'] for x in ('name', 'source'))

            else:
                # this transformation is dynamic and a group
                assert all(x in c for x in ('name', 'type', 'children', 'attributes'))
                assert 'group' == c['type']
                attrs = c['attributes']
                assert len(attrs) == 5

                dep = deps[c['name']]
                d = {
                    'NX_class': 'NXgroup',
                    'depends_on': dep[0],
                    'vector': dep[1],
                    'transformation_type': dep[2],
                    'units': 'm' if dep[2] == 'translation' else 'degrees',
                }
                for k, v in d.items():
                    assert sum(a['name'] == k for a in attrs) == 1
                    attr = next(a for a in attrs if a['name'] == k)
                    assert attr['values'] == v

                # The children should contain a link to the log ... is the order important?
                # Must the number of children always be the same?
                assert all('module' in cc for cc in c['children'])
                assert sum('link' == cc['module'] for cc in c['children']) <= 1
                for cc in c['children']:
                    if 'link' == cc['module']:
                        assert all(x in cc['config'] for x in ('name', 'source'))
