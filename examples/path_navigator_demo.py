"""Example usage of NexusStructureNavigator for path-based access to NeXus Structure JSON."""

from mccode_antlr.loader import parse_mcstas_instr
from moreniius import to_nexus_structure, NexusStructureNavigator

# Define a simple instrument
instr_text = """DEFINE INSTRUMENT simple_spectrometer(param1, param2)
TRACE
COMPONENT origin = Arm() AT (0, 0, 0) ABSOLUTE
COMPONENT source = Source_simple() AT (0, 0, 0) RELATIVE origin
COMPONENT mon0 = TOF_monitor(restore_neutron=1) AT (0, 0, 9) RELATIVE source
COMPONENT sample = Arm() AT (0, 0, 80) RELATIVE mon0
END
"""

# Parse and convert to NeXus Structure JSON
instr = parse_mcstas_instr(instr_text)
structure = to_nexus_structure(instr)

# Without NexusStructureNavigator (verbose):
print("Without navigator:")
mon0_verbose = structure['children'][0]['children'][0]['children'][2]
print(f"  mon0 name: {mon0_verbose['name']}")

# With NexusStructureNavigator (clean path-based access):
print("\nWith navigator - path-based access:")
nav = NexusStructureNavigator(structure)

# Path access returns Navigator objects for groups
mon0 = nav['/entry/instrument/mon0']
print(f"  mon0 is Navigator: {isinstance(mon0, NexusStructureNavigator)}")
print(f"  mon0 name: {mon0.structure['name']}")

# Chainable navigation!
print("\nChainable navigation:")
mon0_chained = nav['entry']['instrument']['mon0']
print(f"  nav['entry']['instrument']['mon0'] works!")
print(f"  mon0 name: {mon0_chained.structure['name']}")

# Get the underlying dict with .dict() or .structure
print(f"  Using .dict(): {mon0_chained.dict()['name']}")
print(f"  Using .structure: {mon0_chained.structure['name']}")

# Access attributes with '@' prefix (returns raw dict, not Navigator)
print("\nAttribute access:")
nx_class = nav['/entry/@NX_class']
print(f"  nx_class is dict: {isinstance(nx_class, dict)}")
print(f"  Entry NX_class: {nx_class['values']}")

nx_class = nav['/entry/instrument/mon0/@NX_class']
print(f"  mon0 NX_class: {nx_class['values']}")

# Can also access attributes from Navigator objects
nx_class_from_nav = mon0['@NX_class']
print(f"  mon0['@NX_class']: {nx_class_from_nav['values']}")

# Check if paths exist
print(f"\n  Path exists /entry/instrument/mon0: {nav.exists('/entry/instrument/mon0')}")
print(f"  Path exists /entry/instrument/missing: {nav.exists('/entry/instrument/missing')}")
print(f"  Attribute exists /entry/@NX_class: {nav.exists('/entry/@NX_class')}")

# Get with default value
result = nav.get('/entry/instrument/nonexistent', default={'fallback': True})
print(f"\n  Get nonexistent path with default: {result}")

# Find all elements with a specific name
mon_results = nav.find_all('mon0')
print(f"\n  Found {len(mon_results)} element(s) named 'mon0'")

# Find all attributes with a specific name
nx_class_attrs = nav.find_all('NX_class', include_attributes=True)
print(f"  Found {len(nx_class_attrs)} NX_class attribute(s)")

# Reverse lookup - get path to an element (requires raw dict)
path = nav.get_path(mon0_chained.structure)
print(f"\n  Path to mon0 element: {path}")

# Reverse lookup for attribute
nx_class_attr = nav['/entry/@NX_class']
attr_path = nav.get_path(nx_class_attr)
print(f"  Path to NX_class attribute: {attr_path}")

# Repr is helpful
print(f"\n  Navigator repr: {repr(mon0)}")
