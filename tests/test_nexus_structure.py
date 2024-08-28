import unittest

# TODO When github.com/g5t/mccode-to-kafka fully switched to using da00, these tests will fail.

class NexusStrctureTestCase(unittest.TestCase):
    def setUp(self):
        from json import dumps
        from mccode_antlr.loader import parse_mcstas_instr
        from mccode_to_kafka.writer import da00_variable_config, da00_dataarray_config
        t0 = {'name': 't', 'unit': 'usec', 'label': 'monitor', 'data': {'first': 0.5, 'last': 10.5, 'size': 11}}
        t1 = {'name': 't', 'unit': 'usec', 'label': 'monitor', 'data': {'first': 1.5, 'last': 11.5, 'size': 11}}
        m0 = da00_dataarray_config(topic='mon0', source='mccode-to-kafka', constants=[da00_variable_config(**t0)])
        m1 = da00_dataarray_config(topic='mon1', source='mccode-to-kafka', constants=[da00_variable_config(**t1)])

        instr = f"""DEFINE INSTRUMENT chopper_spectrometer(
        ch1speed, ch2speed, ch1phase, ch2phase
        )
        TRACE
        COMPONENT origin = Arm() AT (0, 0, 0) ABSOLUTE
        COMPONENT source = Source_simple() AT (0, 0, 0) RELATIVE origin
        COMPONENT mon0 = TOF_monitor(restore_neutron=1) AT (0, 0, 9) RELATIVE source
        METADATA "application/json" "nexus_structure_stream_data" %{{{dumps(m0)}%}}
        COMPONENT ch1 = DiskChopper(theta_0=170, radius=0.35, nu=ch1speed, phase=ch1phase) AT (0, 0, 10) RELATIVE source
        COMPONENT ch2 = DiskChopper(theta_0=170, radius=0.35, nu=ch2speed, phase=ch2phase) AT (0, 0, 0.1) RELATIVE ch1
        COMPONENT mon1 = TOF_monitor(restore_neutron=1) AT (0, 0, 0.1) RELATIVE ch2
        METADATA "application/json" "nexus_structure_stream_data" %{{{dumps(m1)}%}}
        COMPONENT sample = Arm() AT (0, 0, 80) RELATIVE ch2
        END
        """
        self.instr = parse_mcstas_instr(instr)
        self.structures = {'2_mon0': m0, '5_mon1': m1}

    def test_moreniius(self):
        from moreniius import MorEniius
        from moreniius.utils import NotNXdict
        from nexusformat.nexus import NXdata, NXfield
        me = MorEniius.from_mccode(self.instr, origin='sample_stack', only_nx=False, absolute_depends_on=True)
        self.assertTrue(isinstance(me, MorEniius))
        for k in self.structures.keys():
            self.assertTrue(k in me.nx)
            self.assertTrue('data' in me.nx[k])
            a = me.nx[k]['data']
            self.assertTrue(hasattr(a, 'nxclass'))
            self.assertTrue(isinstance(a, NXdata))
            self.assertTrue(isinstance(a.data, NXfield))
            b = a.data.nxdata  # Why did a become an NXdata when it was an NXfield?
            self.assertTrue(isinstance(b, NotNXdict))
            c = b.to_json_dict()
            self.assertTrue(isinstance(c, dict))
            s = self.structures[k]
            self.assertEqual(c, s)

    def test_nexus_structure(self):
        from moreniius.nexus_structure import to_nexus_structure
        nx = to_nexus_structure(self.instr)
        self.assertTrue(isinstance(nx, dict))
        self.assertEqual(len(nx), 1)
        self.assertTrue('children' in nx)
        self.assertEqual(len(nx['children']), 1)
        nx = nx['children'][0]
        group_keys = ('name', 'type', 'children', 'attributes')
        for x in group_keys:
            self.assertTrue(x in nx)
        self.assertEqual(nx['name'], 'entry')
        self.assertEqual(nx['type'], 'group')
        self.assertEqual(len(nx['children']), 1)
        nx = nx['children'][0]
        for x in group_keys:
            self.assertTrue(x in nx)
        self.assertEqual(nx['name'], 'instrument')
        self.assertEqual(len(nx['children']), 9)
        nx = nx['children'][3]
        for x in group_keys:
            self.assertTrue(x in nx)
        self.assertEqual(nx['name'], '2_mon0')
        self.assertEqual(len(nx['children']), 4)  # removed mcstas child
        nx = nx['children'][1] # this is now a NXdata group
        self.assertTrue('attributes' in nx)
        self.assertEqual(len(nx['attributes']), 1)
        self.assertEqual(nx['attributes'][0]['name'], 'NX_class')
        self.assertEqual(nx['attributes'][0]['values'], 'NXdata')
        nx = nx['children'][0]
        self.assertEqual(self.structures['2_mon0'], nx)


if __name__ == '__main__':
    unittest.main()
