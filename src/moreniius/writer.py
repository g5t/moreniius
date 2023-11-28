from zenlog import log


def convert_types(obj, only_nx=True):
    from numpy import dtype, ndarray
    from nexusformat.nexus import NXattr
    py_data_type = type(obj)
    np_data_type = dtype(py_data_type)
    if np_data_type.name == 'object':
        if isinstance(obj, ndarray):
            vl = obj.tolist()
            el = vl[0]
            for ii in range(1, len(obj.shape)):
                el = el[0]
            tp = dtype(type(el)).name
        elif obj is None:
            (tp, vl) = ('string', 'None')
        elif isinstance(obj, NXattr):
            val = obj.nxdata
            if isinstance(val, ndarray):
                val = val.tolist()
            if obj.dtype == 'object':
                (tp, vl) = (dtype(type(obj.nxdata)).name, val)
            else:
                (tp, vl) = (obj.dtype, val)
        elif not only_nx and hasattr(obj, 'to_json_dict'):
            # Shoe-horn in an object-defined dictionary:
            tp, vl = None, obj.to_json_dict()
        else:
            raise RuntimeError(f'unrecognised type {py_data_type} / {np_data_type} for {repr(obj)}')
    else:
        (tp, vl) = (np_data_type.name, obj)
    if tp == 'str':
        tp = 'string'
    elif tp == 'float64':
        tp = 'double'
    elif tp == 'object':
        raise RuntimeError(f'Internal logical error attempting to convert {obj}')
    elif tp == 'int':
        tp = 'int64'
    elif tp == 'float':
        tp = 'double'
    return tp, vl


class Writer:
    """
    Writes out files in various formats from a NeXus structure with instrument information
    """

    def __init__(self, nx_obj):
        from nexusformat.nexus import NXsample, NXentry, NXroot
        self.root_name = 'entry'
        self.instrument = None
        self.data = None
        self.sample = NXsample()
        self.nx_obj = None
        if nx_obj.nxclass == 'NXinstrument':
            self.instrument = nx_obj
            nx_entry = NXentry()
            nx_entry['instrument'] = self.instrument
        else:
            if nx_obj.nxclass == 'NXroot':
                entries = dir(nx_obj)
                if len(entries) > 1:
                    log.warn('More than one entry in nx_obj, using only first entry')
                self.root_name = entries[0]
                self.nx_obj = nx_obj
                nx_entry = nx_obj[self.root_name]
            elif nx_obj.nxclass == 'NXentry':
                nx_entry = nx_obj
            else:
                raise RuntimeError('Input must be an NXroot, NXentry or NXinstrument')
            for x in ('instrument', 'data', 'sample'):
                if hasattr(nx_entry, x):
                    setattr(self, x, nx_entry[x])

        if self.instrument is None:
            raise RuntimeError('No instrument found')

        if self.nx_obj is None:
            self.nx_obj = NXroot()
            self.nx_obj[self.root_name] = nx_entry

    def to_json(self, filename, indent=4, only_nx=True, absolute_depends_on=False):
        """Convert a NeXus object to a JSON-compatible dictionary, then write that to file

        Parameters:
            filename: str - where to write the JSON string, '.json' will be appended if not present
            indent: int - nested JSON indentation depth, default 4
            only_nx: bool - whether non-NeXus objects found in the tree raise an error, default=True
            absolute_depends_on: bool - if True expand `depends_on` clauses to absolute paths
        """
        from json import dumps
        if not filename.endswith('.json'):
            filename = f'{filename}.json'
        to_write = dumps(self.to_nexus_structure(only_nx, absolute_depends_on), indent=indent)
        with open(filename, 'w') as file:
            file.write(to_write)

    def to_nexus_structure(self, only_nx=True, absolute_depends_on=False):
        """Convert a NeXus object to a JSON-compatible 'NeXus-Structure' dictionary as used by the ESS file-writer"""
        json_dict = self._to_json_dict(self.nx_obj, only_nx=only_nx, absolute_depends_on=absolute_depends_on)
        return dict(children=json_dict)

    def _to_json_dict(self, top_obj, only_nx=True, absolute_depends_on=False):
        """Recursive transversal of NXobject tree conversion to JSON-compatible dict"""
        # Note to Greg, depends_on can be data or attribute
        children = []
        for name, obj in top_obj.items():
            if hasattr(obj, 'nxclass'):
                attrs = []
                if absolute_depends_on and 'depends_on' == name and not obj.nxdata.startswith('/'):
                    obj.nxdata = _to_absolute(top_obj.nxpath, obj.nxdata)
                if obj.nxclass == 'NXfield':
                    # print(f'to_json_dict for NXfield {name=}')
                    typ, val = convert_types(obj.nxdata, only_nx)
                    # typ is None if obj.nxdata is a NotNXdict (such that val _is_ the contained dict)
                    entry = dict(module='dataset', config=dict(name=name, values=val, type=typ)) if typ else val
                else:
                    entry = dict(name=name, type='group')
                    attrs = [dict(name='NX_class', dtype='string', values=obj.nxclass)]
                    if len(list(obj)):
                        entry['children'] = self._to_json_dict(obj, only_nx=only_nx, absolute_depends_on=absolute_depends_on)
                for n, v in obj.attrs.items():
                    # print(f'to_json_dict for attribute of {name=}, named {n=}')
                    typ, val = convert_types(v, only_nx)
                    if absolute_depends_on and n == 'depends_on' and '/' != val[0]:
                        val = _to_absolute(top_obj.nxpath, val)
                    attrs.append(dict(name=n, dtype=typ, values=val) if typ else val)
                if len(attrs):
                    entry['attributes'] = attrs
            elif not only_nx and hasattr(obj, 'to_json_dict'):
                # This branch is unreachable because any Python object added to a NXobject gets wrapped in NXfield
                entry = obj.to_json_dict()
            else:
                raise RuntimeError(f'Unrecognized object key {name}')
            children.append(entry)
        return children


def _to_absolute(parent: str, path: str):
    if '.' == path:
        return '.'
    return f'{parent}/{path}'
