"""The heat map's area: the City of Milton Keynes, the unitary authority (LAD24 E06000042, ONS Local Authority Districts
December 2024, full resolution clipped; data/mk/extent/lad24_milton_keynes_27700.geojson). Jacob, 18 Oct 2026: "please
do the full expansive greater MK definition"; offered the borough (309 km2, city status by Letters Patent of 15 Aug
2022) or the 2011 ONS built-up area in 2022 geography (69 km2), he chose the borough. Until then the area was the ONS
2022 built-up areas of Milton Keynes, Bletchley, Newport Pagnell, Wavendon and Woburn Sands, clipped to the lidar.
make_crops.py and package.py take it from here.
"""
import json, os
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

NAME = "Milton Keynes"


CITY = {"Milton Keynes", "Bletchley", "Newport Pagnell", "Wavendon", "Woburn Sands"}


def area(H: Path):
    """the area's outline in British National Grid, holes filled (H: data/mk/heat); HEAT_AREA=bua22 gives the city's
    earlier area, for a run of the city's tiles before the borough's are made"""
    if os.environ.get("HEAT_AREA") == "bua22":
        f = json.load(open(H.parent / "extent" / "bua22_mk_area_27700.geojson"))["features"]
        g = unary_union([shape(x["geometry"]) for x in f if x["properties"]["BUA22NM"] in CITY])
    else:
        g = shape(json.load(open(H.parent / "extent" / "lad24_milton_keynes_27700.geojson"))["features"][0]["geometry"])
    return unary_union([Polygon(q.exterior) for q in (g.geoms if hasattr(g, "geoms") else [g])])


def urban(H: Path):
    """the area's urban part, for figures of where most of its people live (Jacob, 19 Oct 2026: "maybe split the figures
    between the urban core and the greater extent. because not many people live in the rural bits"): the 2021 output
    areas the ONS Rural Urban Classification 2021 calls urban (in a built-up area of 10,000 people or more, or densely
    housed), 812 of the borough's 874, one piece of 118 km2 with the parks between the estates (data/mk/extent/
    oa21_ruc21_milton_keynes_27700.geojson, ONS OA_2021_EW_BFE_V9_RUC, 19 Oct 2026). The 2022 built-up areas were not
    used: they leave out those parks (160 pieces for Milton Keynes alone), and with them the redways' footpaths"""
    f = json.load(open(H.parent / "extent" / "oa21_ruc21_milton_keynes_27700.geojson"))["features"]
    g = unary_union([shape(x["geometry"]) for x in f if x["properties"]["Urban_rura"] == "Urban"])
    return unary_union([Polygon(q.exterior) for q in (g.geoms if hasattr(g, "geoms") else [g])]).intersection(area(H))
