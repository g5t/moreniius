"""Tests for NeXus Structure JSON path navigation utility."""

import unittest
from moreniius.path_navigator import NexusStructureNavigator


class PathNavigatorTestCase(unittest.TestCase):
    """Test cases for NexusStructureNavigator."""
    
    def setUp(self):
        """Create a sample NeXus Structure JSON for testing."""
        self.structure = {
            'children': [
                {
                    'name': 'entry',
                    'type': 'group',
                    'attributes': [
                        {'name': 'NX_class', 'dtype': 'string', 'values': 'NXentry'}
                    ],
                    'children': [
                        {
                            'name': 'instrument',
                            'type': 'group',
                            'attributes': [
                                {'name': 'NX_class', 'dtype': 'string', 'values': 'NXinstrument'}
                            ],
                            'children': [
                                {
                                    'name': 'mon0',
                                    'type': 'group',
                                    'attributes': [
                                        {'name': 'NX_class', 'dtype': 'string', 'values': 'NXmonitor'}
                                    ],
                                    'children': [
                                        {
                                            'module': 'dataset',
                                            'config': {
                                                'name': 'data',
                                                'values': [1, 2, 3],
                                                'type': 'int32'
                                            }
                                        },
                                        {
                                            'name': 'subgroup',
                                            'type': 'group',
                                            'children': []
                                        }
                                    ]
                                },
                                {
                                    'name': 'source',
                                    'type': 'group',
                                    'attributes': [
                                        {'name': 'NX_class', 'dtype': 'string', 'values': 'NXsource'}
                                    ],
                                    'children': [
                                        {
                                            'module': 'link',
                                            'config': {
                                                'name': 'distance',
                                                'source': '/entry/instrument/mon0/data'
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        self.nav = NexusStructureNavigator(self.structure)
    
    def test_root_access(self):
        """Test accessing the root."""
        result = self.nav['']
        # Root access returns self (Navigator)
        self.assertIsInstance(result, NexusStructureNavigator)
        self.assertEqual(result.structure, self.structure)
        
        result = self.nav['/']
        self.assertIsInstance(result, NexusStructureNavigator)
        self.assertEqual(result.structure, self.structure)
    
    def test_simple_path(self):
        """Test accessing simple paths."""
        entry = self.nav['entry']
        self.assertIsInstance(entry, NexusStructureNavigator)
        self.assertEqual(entry.structure['name'], 'entry')
        self.assertEqual(entry.structure['type'], 'group')
        
        entry_slash = self.nav['/entry']
        self.assertIsInstance(entry_slash, NexusStructureNavigator)
        self.assertEqual(entry_slash.structure, entry.structure)
    
    def test_nested_path(self):
        """Test accessing nested paths."""
        instrument = self.nav['entry/instrument']
        self.assertIsInstance(instrument, NexusStructureNavigator)
        self.assertEqual(instrument.structure['name'], 'instrument')
        self.assertEqual(instrument.structure['type'], 'group')
        
        mon0 = self.nav['/entry/instrument/mon0']
        self.assertIsInstance(mon0, NexusStructureNavigator)
        self.assertEqual(mon0.structure['name'], 'mon0')
        self.assertEqual(mon0.structure['type'], 'group')
    
    def test_dataset_access(self):
        """Test accessing datasets (module='dataset')."""
        data = self.nav['/entry/instrument/mon0/data']
        self.assertEqual(data['module'], 'dataset')
        self.assertEqual(data['config']['name'], 'data')
        self.assertEqual(data['config']['values'], [1, 2, 3])
    
    def test_link_access(self):
        """Test accessing links (module='link')."""
        distance = self.nav['/entry/instrument/source/distance']
        self.assertEqual(distance['module'], 'link')
        self.assertEqual(distance['config']['name'], 'distance')
    
    def test_subgroup_access(self):
        """Test accessing nested groups."""
        subgroup = self.nav['/entry/instrument/mon0/subgroup']
        self.assertIsInstance(subgroup, NexusStructureNavigator)
        self.assertEqual(subgroup.structure['name'], 'subgroup')
        self.assertEqual(subgroup.structure['type'], 'group')
    
    def test_nonexistent_path(self):
        """Test that accessing nonexistent paths raises KeyError."""
        with self.assertRaises(KeyError) as ctx:
            _ = self.nav['/entry/nonexistent']
        self.assertIn('nonexistent', str(ctx.exception))
        
        with self.assertRaises(KeyError):
            _ = self.nav['/entry/instrument/mon0/missing']
    
    def test_get_with_default(self):
        """Test get method with default value."""
        result = self.nav.get('/entry/instrument/mon0')
        self.assertIsInstance(result, NexusStructureNavigator)
        self.assertEqual(result.structure['name'], 'mon0')
        
        result = self.nav.get('/entry/nonexistent', 'default')
        self.assertEqual(result, 'default')
        
        result = self.nav.get('/entry/nonexistent')
        self.assertIsNone(result)
    
    def test_exists(self):
        """Test exists method."""
        self.assertTrue(self.nav.exists('/entry'))
        self.assertTrue(self.nav.exists('/entry/instrument/mon0'))
        self.assertTrue(self.nav.exists('/entry/instrument/mon0/data'))
        self.assertTrue(self.nav.exists('/entry/instrument/source/distance'))
        
        self.assertFalse(self.nav.exists('/entry/nonexistent'))
        self.assertFalse(self.nav.exists('/entry/instrument/mon0/missing'))
    
    def test_find_all(self):
        """Test finding all elements with a given name."""
        # Find 'data'
        results = self.nav.find_all('data')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['module'], 'dataset')
        
        # Find 'mon0'
        results = self.nav.find_all('mon0')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'mon0')
        
        # Find something that doesn't exist
        results = self.nav.find_all('nonexistent')
        self.assertEqual(len(results), 0)
    
    def test_get_path(self):
        """Test reverse lookup - getting path to an element."""
        mon0 = self.nav['/entry/instrument/mon0']
        # get_path expects the raw dict, not the Navigator
        path = self.nav.get_path(mon0.structure)
        self.assertEqual(path, '/entry/instrument/mon0')
        
        data = self.nav['/entry/instrument/mon0/data']
        path = self.nav.get_path(data)
        self.assertEqual(path, '/entry/instrument/mon0/data')
        
        # Test with element not in structure
        fake_element = {'name': 'fake', 'type': 'group'}
        path = self.nav.get_path(fake_element)
        self.assertIsNone(path)
    
    def test_structure_property(self):
        """Test accessing the underlying structure."""
        self.assertEqual(self.nav.structure, self.structure)
    
    def test_attribute_access(self):
        """Test accessing attributes with '@' prefix."""
        # Access NX_class attribute on entry
        nx_class = self.nav['/entry/@NX_class']
        self.assertEqual(nx_class['name'], 'NX_class')
        self.assertEqual(nx_class['values'], 'NXentry')
        
        # Access NX_class on instrument
        nx_class = self.nav['/entry/instrument/@NX_class']
        self.assertEqual(nx_class['name'], 'NX_class')
        self.assertEqual(nx_class['values'], 'NXinstrument')
        
        # Access NX_class on mon0
        nx_class = self.nav['/entry/instrument/mon0/@NX_class']
        self.assertEqual(nx_class['name'], 'NX_class')
        self.assertEqual(nx_class['values'], 'NXmonitor')
    
    def test_attribute_not_found(self):
        """Test that accessing nonexistent attributes raises KeyError."""
        with self.assertRaises(KeyError) as ctx:
            _ = self.nav['/entry/@nonexistent']
        self.assertIn('nonexistent', str(ctx.exception))
    
    def test_attribute_must_be_at_end(self):
        """Test that attributes can only be at the end of path."""
        with self.assertRaises(KeyError) as ctx:
            _ = self.nav['/entry/@NX_class/something']
        self.assertIn('must be at the end', str(ctx.exception))
    
    def test_attribute_exists(self):
        """Test exists method with attributes."""
        self.assertTrue(self.nav.exists('/entry/@NX_class'))
        self.assertTrue(self.nav.exists('/entry/instrument/@NX_class'))
        self.assertTrue(self.nav.exists('/entry/instrument/mon0/@NX_class'))
        
        self.assertFalse(self.nav.exists('/entry/@nonexistent'))
    
    def test_attribute_get(self):
        """Test get method with attributes."""
        result = self.nav.get('/entry/@NX_class')
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'NX_class')
        
        result = self.nav.get('/entry/@nonexistent', 'default')
        self.assertEqual(result, 'default')
    
    def test_find_all_attributes(self):
        """Test finding attributes with find_all."""
        # Find without including attributes (should find nothing)
        results = self.nav.find_all('NX_class', include_attributes=False)
        self.assertEqual(len(results), 0)
        
        # Find with including attributes
        results = self.nav.find_all('NX_class', include_attributes=True)
        self.assertGreater(len(results), 0)
        # Should find NX_class on entry, instrument, mon0, source, etc.
        self.assertGreaterEqual(len(results), 3)
        for result in results:
            self.assertEqual(result['name'], 'NX_class')
            self.assertIn('values', result)
    
    def test_get_path_for_attribute(self):
        """Test reverse lookup for attributes."""
        nx_class = self.nav['/entry/instrument/mon0/@NX_class']
        path = self.nav.get_path(nx_class)
        self.assertEqual(path, '/entry/instrument/mon0/@NX_class')
    
    def test_chaining_navigation(self):
        """Test chainable navigation returns Navigator objects."""
        # Single level chaining
        entry = self.nav['entry']
        self.assertIsInstance(entry, NexusStructureNavigator)
        self.assertEqual(entry.structure['name'], 'entry')
        
        # Multi-level chaining
        mon0 = self.nav['entry']['instrument']['mon0']
        self.assertIsInstance(mon0, NexusStructureNavigator)
        self.assertEqual(mon0.structure['name'], 'mon0')
        
        # Mixed chaining and path
        instrument = self.nav['entry']['instrument']
        mon0_from_instrument = instrument['mon0']
        self.assertIsInstance(mon0_from_instrument, NexusStructureNavigator)
        self.assertEqual(mon0_from_instrument.structure['name'], 'mon0')
    
    def test_dict_method(self):
        """Test .dict() method returns underlying dictionary."""
        entry = self.nav['entry']
        self.assertIsInstance(entry, NexusStructureNavigator)
        
        entry_dict = entry.dict()
        self.assertIsInstance(entry_dict, dict)
        self.assertEqual(entry_dict['name'], 'entry')
        self.assertEqual(entry_dict['type'], 'group')
        
        # dict() should be equivalent to .structure property
        self.assertEqual(entry.dict(), entry.structure)
    
    def test_attributes_return_raw_dict(self):
        """Test that attributes return raw dicts, not Navigators."""
        nx_class = self.nav['/entry/@NX_class']
        self.assertIsInstance(nx_class, dict)
        self.assertNotIsInstance(nx_class, NexusStructureNavigator)
        self.assertEqual(nx_class['name'], 'NX_class')
    
    def test_datasets_return_raw_dict(self):
        """Test that datasets return raw dicts, not Navigators."""
        data = self.nav['/entry/instrument/mon0/data']
        self.assertIsInstance(data, dict)
        self.assertNotIsInstance(data, NexusStructureNavigator)
        self.assertEqual(data['module'], 'dataset')
    
    def test_repr(self):
        """Test __repr__ provides useful information."""
        entry = self.nav['entry']
        repr_str = repr(entry)
        self.assertIn('entry', repr_str)
        self.assertIn('NexusStructureNavigator', repr_str)


class PathNavigatorRealWorldTestCase(unittest.TestCase):
    """Test with real NeXus structures from the existing tests."""
    
    def setUp(self):
        """Create a real NeXus Structure from the test instrument."""
        from json import dumps
        from mccode_antlr.loader import parse_mcstas_instr
        from moreniius.nexus_structure import to_nexus_structure
        
        # This is from test_nexus_structure.py
        instr_text = """DEFINE INSTRUMENT chopper_spectrometer(
        ch1speed, ch2speed, ch1phase, ch2phase
        )
        TRACE
        COMPONENT origin = Arm() AT (0, 0, 0) ABSOLUTE
        COMPONENT source = Source_simple() AT (0, 0, 0) RELATIVE origin
        COMPONENT mon0 = TOF_monitor(restore_neutron=1) AT (0, 0, 9) RELATIVE source
        COMPONENT ch1 = DiskChopper(theta_0=170, radius=0.35, nu=ch1speed, phase=ch1phase) AT (0, 0, 10) RELATIVE source
        COMPONENT ch2 = DiskChopper(theta_0=170, radius=0.35, nu=ch2speed, phase=ch2phase) AT (0, 0, 0.1) RELATIVE ch1
        COMPONENT mon1 = TOF_monitor(restore_neutron=1) AT (0, 0, 0.1) RELATIVE ch2
        COMPONENT sample = Arm() AT (0, 0, 80) RELATIVE ch2
        END
        """
        self.instr = parse_mcstas_instr(instr_text)
        self.structure = to_nexus_structure(self.instr)
        self.nav = NexusStructureNavigator(self.structure)
    
    def test_real_structure_navigation(self):
        """Test navigating the real structure."""
        # Access entry
        entry = self.nav['/entry']
        self.assertIsInstance(entry, NexusStructureNavigator)
        self.assertEqual(entry.structure['name'], 'entry')
        self.assertEqual(entry.structure['type'], 'group')
        
        # Access instrument
        instrument = self.nav['/entry/instrument']
        self.assertIsInstance(instrument, NexusStructureNavigator)
        self.assertEqual(instrument.structure['name'], 'instrument')
        self.assertEqual(instrument.structure['type'], 'group')
        
        # Access mon0
        mon0 = self.nav['/entry/instrument/mon0']
        self.assertIsInstance(mon0, NexusStructureNavigator)
        self.assertEqual(mon0.structure['name'], 'mon0')
        self.assertEqual(mon0.structure['type'], 'group')
    
    def test_real_structure_exists(self):
        """Test path existence checks on real structure."""
        self.assertTrue(self.nav.exists('/entry'))
        self.assertTrue(self.nav.exists('/entry/instrument'))
        self.assertTrue(self.nav.exists('/entry/instrument/mon0'))
        self.assertTrue(self.nav.exists('/entry/instrument/mon1'))
        self.assertTrue(self.nav.exists('/entry/instrument/sample'))
        
        self.assertFalse(self.nav.exists('/entry/nonexistent'))
    
    def test_real_structure_find_all(self):
        """Test finding components in real structure."""
        # Find all monitors
        mon0_results = self.nav.find_all('mon0')
        self.assertGreater(len(mon0_results), 0)
        
        mon1_results = self.nav.find_all('mon1')
        self.assertGreater(len(mon1_results), 0)


if __name__ == '__main__':
    unittest.main()
