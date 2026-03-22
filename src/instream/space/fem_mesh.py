"""FEM mesh reader for River2D (.2dm) and GMSH (.msh) formats.

Requires: pip install meshio
"""



class FEMMesh:
    """Read a finite element mesh and produce CellState + neighbor indices.

    Not yet implemented. When complete, this will be an alternative to
    PolygonMesh for loading habitat geometry from FEM simulation output.

    Supported formats (planned):
    - River2D .2dm (SMS format)
    - GMSH .msh
    - Any format supported by meshio

    Usage (planned):
        mesh = FEMMesh("river.2dm", reach_field="material_id")
        cell_state = mesh.to_cell_state(depth_flows, depth_values, vel_flows, vel_values)
        fem_space = FEMSpace(cell_state, mesh.neighbor_indices)
    """

    def __init__(self, mesh_path, **kwargs):
        raise NotImplementedError(
            "FEMMesh reader not yet implemented. "
            "Use PolygonMesh with shapefile input instead. "
            "To implement: pip install meshio, then read triangular elements, "
            "compute centroids, areas, and adjacency from element connectivity."
        )

    @property
    def num_cells(self):
        raise NotImplementedError

    @property
    def neighbor_indices(self):
        raise NotImplementedError

    def to_cell_state(self, depth_flows, depth_values, vel_flows, vel_values):
        raise NotImplementedError
