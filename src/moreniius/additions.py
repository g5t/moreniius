from zenlog import log
from .mccode.instance import COMPONENT_TYPE_NAME_TO_NEXUS, register_translator
from .mccode.comp import monitor_translator

log.debug('Extending moreniius.mccode.NXInstance translators')

# Tell the converter about missing component(s)
COMPONENT_TYPE_NAME_TO_NEXUS['ESS_butterfly'] = 'NXmoderator'


def readout_translator(instance):
    """BIFROST specific Readout Master, should be deprecated in favour of ReadoutCAEN"""
    from nexusformat.nexus import NXgroup
    from .utils import ev44_stream_specifier
    stream = ev44_stream_specifier(source='caen', topic='SimulatedEvents')

    # Somehow define the NXdetector_module ... :/

    return NXgroup(data=stream)


def monochromator_rowland_translator(nxinstance):
    from nexusformat.nexus import NXcrystal
    from .nxoff import NXoff
    h = nxinstance.nx_parameter('yheight') / 2
    w = nxinstance.nx_parameter('zwidth') / 2
    count = nxinstance.nx_parameter('NH')
    gap = nxinstance.nx_parameter('gap')

    crystal = NXcrystal()
    crystal['usage'] = 'Bragg'
    crystal['d_spacing'] = nxinstance.nx_parameter('DM')
    crystal['d_spacing'].units = 'angstrom'
    crystal['segment_width'] = w * 2
    crystal['segment_width'].units = 'm'
    crystal['segment_height'] = h * 2
    crystal['segment_height'].units = 'm'
    crystal['segment_gap'] = gap
    crystal['segment_gap'].units = 'm'
    crystal['segment_columns'] = count
    crystal['segment_rows'] = nxinstance.nx_parameter('NV')
    mosaic_h = nxinstance.nx_parameter('mosaich')
    mosaic_v = nxinstance.nx_parameter('mosaicv')
    mosaic = nxinstance.nx_parameter('mosaic')
    crystal['mosaic_horizontal'] = mosaic_h if mosaic_h else mosaic
    crystal['mosaic_horizontal'].units = 'arcminutes'
    crystal['mosaic_vertical'] = mosaic_v if mosaic_v else mosaic
    crystal['mosaic_vertical'].units = 'arcminutes'
    # ... could add curvature by copying calculation ... but we don't have source or sink distances here.

    # nexus-constructor does not use any of the segment information in its drawing -- so we need to specify OFF
    # the danger of course is that without the distances we *can't* get the rowland geometry right and someone might
    # assume that the OFF is more-valid than the McStas data :/
    vertices = []
    faces = []
    for i in range(count):
        x0 = (i - count // 2) * (2 * w + gap)
        # "For an unrotated monochromator component, the crystal surface lies in the Y-Z plane" -- McDoc
        vertices.extend([[0, -h, x0 - w], [0, -h, x0 + w], [0, h, x0 + w], [0, h, x0 - w]])
        faces.append([4*i, 4*i+1, 4*i+2, 4*i+3])

    geometry = NXoff(vertices, faces)
    crystal['geometry'] = geometry.to_nexus()

    return crystal


def bifrost_pixel_regex_20230703():
    from re import compile
    # This is highly specialized to BIFROST_nxs as of 2023-07-03
    # where we always have "WHEN (# == secondary_cassette && # == analyzer)
    w = r"WHEN \((?P<cassette>[0-9]+)\s*==\s*secondary_cassette\s*&&\s*(?P<analyzer>[0-9]+)\s*==\s*analyzer\)"
    r = compile(w)

    def icd_pixel(resolution, arc, triplet, tube, position):
        # position takes values between 0 and resolution - 1
        return 27 * resolution * arc + 9 * resolution * tube + resolution * triplet + position + 1

    return icd_pixel, r


def bifrost_pixel_regex_20230911():
    from re import compile
    # This is highly specialized to BIFROST_nxs as of 2023-07-03
    # where we always have "WHEN (# == secondary_cassette && # == analyzer)
    w = r"(?P<cassette>[0-9]+)\s*==\s*secondary_cassette\s*&&\s*(?P<analyzer>[0-9]+)\s*==\s*analyzer"
    r = compile(w)

    def icd_pixel(resolution, arc, triplet, tube, position):
        # position takes values between 0 and resolution - 1
        return 27 * resolution * arc + 9 * resolution * tube + resolution * triplet + position + 1

    return icd_pixel, r


def bifrost_source_20230704(arc, triplet):
    return f"arc={arc};triplet={triplet}"


def detector_tubes_offsets_and_one_cylinder(self):
    import numpy as np
    from nexusformat.nexus import NXdetector, NXfield, NXcylindrical_geometry
    from .utils import ev44_stream_specifier
    # parameters for NXdetector, to be filled-in
    pars = {}
    pixel_fun, wre = bifrost_pixel_regex_20230911()

    cassette = 1
    analyzer = 1
    if wre.match(str(self.obj.when)):
        m = wre.match(str(self.obj.when))
        cassette = int(m.group('cassette'))
        analyzer = int(m.group('analyzer'))

    # cassette in (1, 9), analyzer in (1, 5):

    # i is the 'slow' direction, j is the 'fast' direction
    # --> i between tubes, j along tubes
    ni = self.nx_parameter('N') # corresponds to 'width' and McStas 'x' axis
    nj = self.nx_parameter('no')  # corresponds to 'height' and McStas 'y' axis
    width, height, radius = [self.nx_parameter(n) for n in ('width', 'height', 'radius')]

    halfi = (width - 2 * radius) / 2
    di = np.linspace(-halfi, halfi, ni)
    dj = np.linspace(-height / 2, height / 2, nj)
    Dj, Di = np.meshgrid(dj, di)

    arc, triplet = analyzer - 1, cassette - 1  # naming from ICD 01 v6 indexing of triplets

    diameter = f'2 * {radius}' if isinstance(radius, str) else 2 * radius

    pars['detector_number'] = [[pixel_fun(nj, arc, triplet, tube, position) for position in range(nj)] for tube in
                               range(ni)]
    pars['data'] = ev44_stream_specifier(bifrost_source_20230704(arc, triplet), 'SimulatedEvents')
    pars['x_pixel_offset'] = NXfield(Di, units='m')
    pars['y_pixel_offset'] = NXfield(Dj, units='m')
    pars['x_pixel_size'] = NXfield(diameter, units='m')
    pars['y_pixel_size'] = NXfield(height / nj, units='m')
    pars['diameter'] = NXfield(diameter, units='m')
    pars['type'] = f'{ni} He3 tubes in series' if self.nx_parameter('wires_in_series') else f'{ni} He3 tubes'

    # use NXcylindrical_geometry to define the detectors, which requires:
    #   vertices - (i, 3) -- points relative to the detector position defining each cylinder in the detector
    #   cylinders - (j, 3) -- indexes of the vertices, to define a cylinder by its face-center, face-edge, and
    #                         opposite face center:
    #             |---------------|
    #             |               |
    #           0 +               + 2
    #             |               |
    #           1 |---------------|
    #   detector_number: (k,) -- maps the cylinders in cylinder by index with a detector id
    #
    # We're allowed to specify a single cylinder then le the x/y/z_offset position that pixel repeatedly:
    dy = (dj[1] - dj[0]) / 2
    vertices = NXfield([[0, -dy, 0], [radius, -dy, 0], [0, dy, 0]], units='m')
    cylinders = [[0, 1, 2]]
    geometry = NXcylindrical_geometry(vertices=vertices, cylinders=cylinders)

    return NXdetector(**pars, geometry=geometry)


def detector_tubes_only_cylinder(self):
    """This results in only the first cylinder being plotted by Nexus constructor"""
    import numpy as np
    from nexusformat.nexus import NXdetector, NXfield, NXcylindrical_geometry
    from .utils import ev44_stream_specifier
    # parameters for NXdetector, to be filled-in
    pars = {}
    pixel_fun, wre = bifrost_pixel_regex_20230911()

    if wre.match(str(self.obj.when)):
        m = wre.match(str(self.obj.when))
        cassette = int(m.group('cassette'))
        analyzer = int(m.group('analyzer'))
    else:
        cassette = 1
        analyzer = 1
    # cassette in (1, 9), analyzer in (1, 5):

    # i is the 'slow' direction, j is the 'fast' direction
    # --> i between tubes, j along tubes
    ni = self.nx_parameter('N') # corresponds to 'width' and McStas 'x' axis
    nj = self.nx_parameter('no')  # corresponds to 'height' and McStas 'y' axis
    width, height, radius = [self.nx_parameter(n) for n in ('width', 'height', 'radius')]
    halfi = (width - 2 * radius) / 2
    di = np.linspace(-halfi, halfi, ni)
    dj = np.linspace(-height / 2, height / 2, nj+1)

    # use NXcylindrical_geometry to define the detectors, which requires:
    #   vertices - (i, 3) -- points relative to the detector position defining each cylinder in the detector
    #   cylinders - (j, 3) -- indexes of the vertices, to define a cylinder by its face-center, face-edge, and
    #                         opposite face center:
    #             |---------------|---------------|
    #             |               |               |
    #           0 +               + 2             + 4
    #             |               |               |
    #             |---------------|---------------|
    #             1               3               5
    #   detector_number: (k,) -- maps the cylinders in cylinder by index with a detector id

    arc, triplet = analyzer - 1, cassette - 1  # naming from ICD 01 v6 indexing of triplets

    vertices = NXfield([v for x in di for y in dj for v in [[x, y, 0], [x, y, radius]]], units='m')
    cylinders = [[k, k+1, k+2] for k in [tube * 2 * (nj + 1) + 2 * j for tube in range(ni) for j in range(nj)]]
    detector_number = [pixel_fun(nj, arc, triplet, tube, j) for tube in range(ni) for j in range(nj)]

    pars['data'] = ev44_stream_specifier(bifrost_source_20230704(arc, triplet), 'SimulatedEvents')
    pars['type'] = f'{ni} He3 tubes in series' if self.nx_parameter('wires_in_series') else f'{ni} He3 tubes'

    geometry = NXcylindrical_geometry(vertices=vertices, cylinders=cylinders, detector_number=detector_number)

    return NXdetector(**pars, geometry=geometry)


# def histogram_monitor(obj):
#     from nexusformat.nexus import NXmonitor
#     from .nxoff import NXoff
#     from .utils import ev44_stream_specifier
#     width = obj.nx_parameter('xwidth')
#     height = obj.nx_parameter('yheight')
#     geometry = NXoff.from_wedge(l=0.005, w1=width, h1=height)
#
#     # parameters to be filled-in
#     pars = {}
#     # pars['data'] = ev44_stream_specifier(bifrost_source_20230704(arc, triplet), 'SimulatedEvents')
#     # pars['type'] = f'{ni} He3 tubes in series' if self.nx_parameter('wires_in_series') else f'{ni} He3 tubes'
#     pars['geometry'] = geometry.to_nexus()
#     return NXmonitor(**pars)


# Patch-in the new methods
register_translator('Readout', readout_translator)
register_translator('Monochromator_Rowland', monochromator_rowland_translator)
register_translator('Detector_tubes', detector_tubes_only_cylinder)
register_translator('Frame_monitor', monitor_translator)

log.debug('moreniius.mccode.NXInstance translators extended')
