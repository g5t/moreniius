# moreniius
A project to contain custom components required to use `eniius` to produce `NeXus Structure` `JSON` from `mccode-antlr` simulated instruments.
Simply, _more_ `eniius`.

## Features

### Path-based Navigation for NeXus Structure JSON

The `NexusStructureNavigator` class provides convenient path-based access to NeXus Structure JSON objects, which have a verbose hierarchical format. It supports both path-based access and chainable navigation.

#### Without Navigator (verbose)
```python
from moreniius import to_nexus_structure, load_instr

structure = to_nexus_structure(load_instr('instrument.instr'))
# Access requires nested dictionary lookups
component = structure['children'][0]['children'][0]['children'][12]

# Accessing attributes is even more verbose
attrs = structure['children'][0]['attributes']
nx_class = next(a for a in attrs if a['name'] == 'NX_class')
```

#### With Navigator (clean and chainable)
```python
from moreniius import to_nexus_structure, load_instr, NexusStructureNavigator

structure = to_nexus_structure(load_instr('instrument.instr'))
nav = NexusStructureNavigator(structure)

# Path-based access (returns Navigator for groups)
component = nav['/entry/instrument/component_name']
field = nav['/entry/instrument/component_name/field']

# Chainable navigation - each group access returns a new Navigator!
component = nav['entry']['instrument']['component_name']

# Get the underlying dictionary
raw_dict = component.dict()  # or component.structure

# Access attributes with '@' prefix (returns raw dict)
nx_class = nav['/entry/@NX_class']
vector = nav['/entry/instrument/something/@vector']

# Attributes can also be accessed from Navigator objects
nx_class = nav['entry']['instrument']['mon0']['@NX_class']

# Check if paths exist
if nav.exists('/entry/instrument/mon0'):
    mon0 = nav['/entry/instrument/mon0']

# Get with default value
result = nav.get('/entry/instrument/missing', default=None)

# Find all elements with a given name
monitors = nav.find_all('mon0')

# Find all attributes with a given name
all_nx_classes = nav.find_all('NX_class', include_attributes=True)

# Reverse lookup - get path to an element (requires raw dict)
path = nav.get_path(component.structure)  # Returns '/entry/instrument/component_name'
attr_path = nav.get_path(nx_class)  # Returns '/entry/@NX_class'
```

**Key behaviors:**
- Accessing a group (has `children`) returns a `NexusStructureNavigator` for chaining
- Accessing an attribute (with `@`), dataset, or link returns the raw dictionary
- Use `.dict()` or `.structure` to get the underlying dictionary from a Navigator

See `examples/path_navigator_demo.py` for a complete working example.
