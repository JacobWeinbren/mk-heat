"""The heat map's area: the City of Milton Keynes, the unitary authority (LAD24 E06000042, ONS Local Authority Districts
December 2024, full resolution clipped; data/mk/extent/lad24_milton_keynes_27700.geojson). Jacob, 18 Oct 2026: "please
do the full expansive greater MK definition"; offered the borough (309 km2, city status by Letters Patent of 15 Aug
2022) or the 2011 ONS built-up area in 2022 geography (69 km2), he chose the borough. Until then the area was the ONS
2022 built-up areas of Milton Keynes, Bletchley, Newport Pagnell, Wavendon and Woburn Sands, clipped to the lidar.
The make_crops, package, treecount and landsat_check scripts take it from here.
"""
import json
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

NAME = "Milton Keynes"


def area(H: Path):
    """the area's outline in British National Grid, holes filled (H: data/mk/heat)"""
    g = shape(json.load(open(H.parent / "extent" / "lad24_milton_keynes_27700.geojson"))["features"][0]["geometry"])
    return unary_union([Polygon(q.exterior) for q in (g.geoms if hasattr(g, "geoms") else [g])])
