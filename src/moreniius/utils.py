from mccode_antlr.instr import Instance


class NotNXdict:
    """Wrapper class to prevent NXfield-parsing of the held dictionary"""
    def __init__(self, v: dict):
        self.value = v

    def to_json_dict(self):
        return self.value

    def __repr__(self):
        return f"NotNXdict<{self.value}>"


def outer_transform_dependency(transformations):
    """For a NXtransformations group, find the most-dependent transformation name

    E.g., for
    transforms:NXtransformations
      rotation_angle
        @depends_on=.
      chi
        @depends_on=rotation_angle
      phi
        @depends_on=chi

    find and return 'phi' since it depends on 'chi', which depends on 'rotation_angle', which is independent

    The dependency chain *must* be singular and fully contained in the NXtransformations object for this to work
    """
    names = list(transformations)
    if len(names) == 1:
        return names[0]
    depends = {name: getattr(transformations, name).depends_on for name in names}
    externals = [v for k, v in depends.items() if v not in depends]
    if len(externals) != 1:
        raise RuntimeError(f"Dependency chain {depends} should have one absolute dependency, found {externals} instead")

    def dep_of(name):
        d = [k for k, v in depends.items() if v == name]
        if len(d) != 1:
            raise RuntimeError(f'Expected one dependency of {name} but found dependencies: {d}')
        return d[0]

    chain = [dep_of(externals[0])]
    while len(chain) < len(names):
        chain.append(dep_of(chain[-1]))
    return chain[-1]


def _sanitize(indict):
    for k in indict:
        if isinstance(indict[k], str):
            indict[k] = indict[k].replace('<nl>', '\n').replace('<tb>', '    ')\
                .replace('<qt>', "'").replace('<bs>', '\\')
        elif isinstance(indict[k], dict):
            indict[k] = _sanitize(indict[k])
    return indict


def dict2NXobj(indict, only_nx=True):
    from nexusformat.nexus import NXfield
    import nexusformat.nexus as nexus
    outdict = {}
    def type_is_ok(t):
        return not only_nx or t.startswith('NX')

    for k, v in indict.items():
        if isinstance(v, dict) and all([f in v for f in ['type', 'value']]) and type_is_ok(v['type']):
            if v['type'] == 'NXfield':
                outdict[k] = NXfield(v['value'], **v.pop('attributes', {}))
            elif not only_nx and v['type'] == 'dict':
                outdict[k] = NotNXdict(v['value'])
            else:
                nxobj = getattr(nexus, v.pop('type'))
                outdict[k] = nxobj(**v.pop('value'))
        else:
            outdict[k] = v
    return outdict


def get_mcstasscript_component_eniius_data(comp):
    """Checks for the post-McStas 3.3 METADATA attribute, and looks there for JSON eniius_data.
    Always checks EXTEND blocks as well, for `char eniius_data[]` style entries
    """
    from re import compile

    ed = 'eniius_data'
    # METADATA is a dict[str, (str, str)] where the keys are 'names' and the tuple is (type, value)
    if hasattr(comp, 'METADATA') and ed in comp.METADATA and comp.METADATA[ed][0].lower() == 'json':
        return comp.METADATA[ed][1]
    # match any '{name}eniius_data{suffix}={encoded data};
    ed_regex = compile(rf'.*{ed}[^=]*=([^;]*);')
    ed_match = ed_regex.match(comp.EXTEND)
    if not ed_match:
        return None
    to_translate = ed_match.group(1)
    # extract the matched group, remove all \n, \, and "; replace all ' by "
    json_str = to_translate.translate(str.maketrans("'", '"', '\n"\\'))
    return json_str


def decode_component_eniius_data(comp, only_nx=True) -> dict:
    """Extract the 'eniius_data' block from the component EXTEND statement

    If found, decode the information and return a dictionary of contained NXobjects
    """
    from json import JSONDecodeError, loads
    json_str = get_mcstasscript_component_eniius_data(comp)
    if json_str is None:
        return {}
    try:
        return dict2NXobj(_sanitize(loads(json_str)), only_nx=only_nx)
    except SyntaxError:
        return {}
    except JSONDecodeError as er:
        print(f"failed to decode\n{json_str}\ndue to error {er}")
        return {}


def mccode_component_eniius_data(comp: Instance, only_nx=True) -> dict:
    """Require that any eniius data comes from a METADATA tag"""
    from json import JSONDecodeError, loads
    json_str = [md.value for md in comp.metadata if md.name == 'eniius_data' and md.mimetype.lower() == 'json']
    if not json_str:
        return {}
    if len(json_str) > 1:
        print(f'{len(json_str)} "eniius_data" METADATA blocks, using only the first one')
    try:
        return dict2NXobj(loads(json_str[0]), only_nx=only_nx)
    except JSONDecodeError as er:
        print(f'Failed to decode {json_str[0]} due to error {er}')
        return {}


def ess_flatbuffer_specifier(module: str, config: dict) -> NotNXdict:
    """ESS uses flat buffers to communicate NeXus file content information, this packages one for eniius processing"""
    return NotNXdict({'module': module, 'config': config})


def ev44_stream_specifier(source: str, topic: str) -> NotNXdict:
    """Produce an EV44 specification, the (latest) Event flat buffer identifier used by ESS

    Parameters:
        source: str
            the name of the event producer, typically matches an instrument detector name
        topic: str
            the name of the Kafka stream on which the to-be-read events are published
    """
    return ess_flatbuffer_specifier('ev44', {'source': source, 'topic': topic})


def link_specifier(name: str, source: str) -> NotNXdict:
    """
    Constructs a specifier to insert a NeXus link into an ESS produced NeXus file

    Parameters:
        name: str
            the name given to the NeXus link, should be unique at its group level
        source: str
            the target of the link, the location in the eventual NeXus file where the source of data resides

    Examples:
    To produce the link in the following NeXus JSON structure, one would use this function
        {
          "name": "data",
          "type": "group",
          "attributes": [
            {
              "name": "NX_class",
              "dtype": "string",
              "values": "NXdata"
            }
          ],
          "children": [
            {
              "module": "link",
              "config": {
                "name": "detector0_event_data",
                "source": "/entry/instrument/detector_panel_0/event_data"
              }
            },
          ]
        }
    one would use this function to produce an NotNXdict that the eniius writer will insert into the resulting JSON
    file _without_ converting its contents to NX* objects first.

    >>> link_specifier('detector0_event_data', '/entry/instrument/detector_panel_0/event_data')
    """
    return ess_flatbuffer_specifier('link', {'name': name, 'source': source})
