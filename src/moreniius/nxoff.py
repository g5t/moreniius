import nexusformat.nexus as nexus

# Only in nexusformat >= 1.0.0
if not hasattr(nexus, 'NXoff_geometry'):
    NXoff_geometry = nexus.tree._makeclass('NXoff_geometry')
else:
    from nexusformat.nexus import NXoff_geometry


class NXoff():
    # Class read/create NXoff_geometry fields using an Object File Format (OFF) syntax
    def __init__(self, vertices, faces):
        self.vertices = vertices
        self.faces = faces

    @classmethod
    def from_nexus(cls, nxfield):
        # Create an OFF structure from a NeXus field
        wo = nxfield.winding_order
        fa = list(nxfield.faces) + [len(wo)]
        faces = [wo[fa[ii]:fa[ii+1]] for ii in range(len(fa)-1)]
        return cls(nxfield.vertices, faces)

    @classmethod
    def from_wedge(cls, l, w1, h1, w2=None, h2=None):
        # Create an OFF structure in shape of a wedge (trapezoidal prism)
        if w2 is None:
            w2 = w1
        if h2 is None:
            h2 = h1
        (x1, y1, x2, y2) = tuple([float(v)/2 for v in [w1, h1, w2, h2]])
        # Sets the origin at the centre of the guide entry square face
        vertices = [[-x1, -y1, 0], [-x1, y1, 0], [x1, y1, 0], [x1, -y1, 0],
                    [-x2, -y2, l], [-x2, y2, l], [x2, y2, l], [x2, -y2, l]]
        # Use a clockwise winding, facing out, beam is in +z direction
        faces = [[0, 1, 2, 3], [1, 5, 6, 2], [5, 4, 7, 6],
                 [6, 7, 3, 2], [7, 4, 0, 3], [1, 0, 4, 5]]
        return cls(vertices, faces)

    @classmethod
    def sphere(cls, radius):
        from numpy import sqrt
        phi = (1 + sqrt(5)) / 2
        r = radius / sqrt(1 + phi)
        p = r * phi
        vertices = [[-r, p, 0], [r, p, 0], [-r, -p, 0], [r, -p, 0],
                    [0, -r, p], [0, r, p], [0, -r, -p], [0, r, -p],
                    [p, 0, -r], [p, 0, r], [-p, 0, -r], [-p, 0, r]]
        faces = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
                 [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
                 [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
                 [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]]
        return cls(vertices, faces)

    def to_nexus(self):
        from numpy import cumsum, array
        from nexusformat.nexus import NXfield
        winding_order = [ww for fa in self.faces for ww in fa]
        faces = [0] + cumsum([len(self.faces[ii]) for ii in range(len(self.faces)-1)]).tolist()
        vertices = NXfield(array(self.vertices, dtype='float64'), units='m')
        return NXoff_geometry(vertices=vertices, winding_order=winding_order, faces=faces)

    @staticmethod
    def _get_width_height(pos):
        from numpy import max, min
        # Gets the width and height (in x and y) of a set of points
        return max(pos[:, 0]) - min(pos[:, 0]), max(pos[:, 1]) - min(pos[:, 1])

    def get_guide_params(self):
        # Gets the guide parameters from the OFF geometry.
        from numpy import array, mean, where, max, min
        ve = array(self.vertices)
        zmean = mean(ve[:, 2])
        w1, h1 = self._get_width_height(ve[where(ve[:, 2] < zmean)[0], :])
        w2, h2 = self._get_width_height(ve[where(ve[:, 2] >= zmean)[0], :])
        l = max(ve[:, 2]) - min(ve[:, 2])
        return w1, h1, w2, h2, l
