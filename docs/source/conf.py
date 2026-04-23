project = "Salmopy"
version = "0.43.8"
release = "0.43.8"
author = "Salmopy Team"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

html_theme = "sphinx_rtd_theme"

autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = True

nitpicky = True
nitpick_ignore = [
    # External library types we don't control
    ("py:class", "numpy.ndarray"),
    ("py:class", "np.ndarray"),
    ("py:class", "numpy.random.Generator"),
    ("py:class", "np.random.Generator"),
    ("py:class", "numpy.random._generator.Generator"),
    ("py:class", "numpy Generator"),
    ("py:class", "datetime.date"),
    ("py:class", "pathlib.Path"),
    ("py:class", "enum.IntEnum"),
    ("py:class", "pydantic.BaseModel"),
    ("py:class", "pydantic.main.BaseModel"),
    ("py:class", "ConfigDict"),
    ("py:class", "pandas.DataFrame"),
    # Our own internal module with a leading-underscore name
    ("py:class", "salmopy.backends._interface.ComputeBackend"),
    # Informal in-docstring types (NumPy-style Parameters sections sometimes
    # use placeholder names like "(N,)" and "float64" as free text rather
    # than proper cross-references). These are documentation conventions,
    # not real type targets. Fixable in a future docstring cleanup pass.
    ("py:class", "N"),
    ("py:class", "array"),
    ("py:class", "arrays"),
    ("py:class", "float64"),
    ("py:class", "mapping name -> GearConfig"),
    # v0.17.0 additions
    ("py:class", "capacity"),
    ("py:class", "num_cells"),
    ("py:class", "dtype bool"),
    ("py:class", "optional bool array"),
    # v0.43.8 additions — remaining autodoc warnings from docstring placeholders
    ("py:class", "shape"),
    ("py:class", "optional"),
    ("py:class", "optional int"),
    ("py:class", "optional float"),
    ("py:class", "optional str"),
    ("py:class", "optional list"),
    ("py:class", "Arc N"),
    ("py:class", "Arc D"),
    ("py:class", "Arc O"),
    ("py:class", "Arc P"),
    ("py:class", "Arc Q"),
    ("py:class", "sequence"),
    ("py:class", "sequence of str"),
    ("py:class", "sequence of float"),
    ("py:class", "callable"),
    ("py:class", "dict"),
    ("py:class", "tuple"),
    ("py:class", "list"),
    ("py:class", "path-like"),
]
