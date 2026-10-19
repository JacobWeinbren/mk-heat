# Milton Keynes in the Heat

How hot Milton Keynes' footpaths, bus stops and open ground felt, hour by hour, on the hottest day of summer 2026, and what more trees and bus shelters would change, across the City of Milton Keynes and its urban area: https://heat.weinbren.me

## References

### Methods

- Lindberg, Holmer and Thorsson (2008). SOLWEIG 1.0 – modelling spatial variations of 3D radiant fluxes and mean radiant temperature in complex urban settings. *International Journal of Biometeorology* 52(7), 697–713. https://doi.org/10.1007/s00484-008-0162-7
- Lindberg and Grimmond (2011). The influence of vegetation and building morphology on shadow patterns and mean radiant temperatures in urban areas: model development and evaluation. *Theoretical and Applied Climatology* 105(3–4), 311–323. https://doi.org/10.1007/s00704-010-0382-8
- Lindberg, Onomura and Grimmond (2016). Influence of ground surface characteristics on the mean radiant temperature in urban areas. *International Journal of Biometeorology* 60(9), 1439–1452. https://doi.org/10.1007/s00484-016-1135-x
- Lindberg et al. (2018). Urban Multi-scale Environmental Predictor (UMEP): an integrated tool for city-based climate services. *Environmental Modelling & Software* 99, 70–87. https://doi.org/10.1016/j.envsoft.2017.09.020
- Ratti and Richens (1999). Urban texture analysis with image processing techniques. In Augenbroe and Eastman (eds), *Computers in Building: Proceedings of the CAADfutures'99 Conference*. Springer, 49–64. https://doi.org/10.1007/978-1-4615-5047-1_4
- Bröde et al. (2012). Deriving the operational procedure for the Universal Thermal Climate Index (UTCI). *International Journal of Biometeorology* 56(3), 481–494. https://doi.org/10.1007/s00484-011-0454-1
- Błażejczyk et al. (2013). An introduction to the Universal Thermal Climate Index (UTCI). *Geographia Polonica* 86(1), 5–10. https://doi.org/10.7163/GPol.2013.1
- Wallenberg, Lindberg and Rayner (2022). Locating trees to mitigate outdoor radiant load of humans in urban areas using a metaheuristic hill-climbing algorithm – introducing TreePlanter v1.0. *Geoscientific Model Development* 15(3), 1107–1128. https://doi.org/10.5194/gmd-15-1107-2022
- Li et al. (2025). PointSSM: state space model for large-scale LiDAR point cloud semantic segmentation. *International Journal of Applied Earth Observation and Geoinformation* 144, 104830. https://doi.org/10.1016/j.jag.2025.104830
- Zhang et al. (2003). A progressive morphological filter for removing nonground measurements from airborne LIDAR data. *IEEE Transactions on Geoscience and Remote Sensing* 41(4), 872–882. https://doi.org/10.1109/TGRS.2003.810682
- Popescu and Wynne (2004). Seeing the trees in the forest: using lidar and multispectral data fusion with local filtering and variable window size for estimating tree height. *Photogrammetric Engineering & Remote Sensing* 70(5), 589–604. https://doi.org/10.14358/PERS.70.5.589
- Otsu (1979). A threshold selection method from gray-level histograms. *IEEE Transactions on Systems, Man, and Cybernetics* 9(1), 62–66. https://doi.org/10.1109/TSMC.1979.4310076
- Highways England (2021). Design Manual for Roads and Bridges, CD 127 Cross-sections and headrooms, version 1.0.1.

### Data

- Environment Agency: National LIDAR Programme, point cloud, surveys P_10737 and P_10738. Open Government Licence v3.0. © Environment Agency copyright and/or database right 2022. All rights reserved.
- Environment Agency: LIDAR Vegetation Object Model (VOM), for its 2.5 m vegetation floor only. Open Government Licence v3.0.
- Met Office: UK Deterministic (UKV) 2 km forecast, 12–14 August 2026, British Crown copyright, CC BY-SA 4.0; through the Open-Meteo Historical Forecast API: Zippenfenig (2023). Open-Meteo.com Weather API. Zenodo. https://doi.org/10.5281/zenodo.7970649. Weather data by Open-Meteo.com (CC BY 4.0).
- OpenStreetMap contributors (ODbL), through the Overpass API.
- Protomaps Basemap v4.15.2, a Planetiler build of OpenStreetMap as of 17 October 2026 (ODbL).
- Department for Transport: National Public Transport Access Nodes (NaPTAN), Milton Keynes (ATCO area 049), October 2026. Open Government Licence v3.0.
- Office for National Statistics: Local Authority Districts (December 2024) Boundaries UK BFC; Output Areas (December 2021) Boundaries EW BFE (V9) and Rural Urban Classification (2021). Source: Office for National Statistics licensed under the Open Government Licence v3.0. Contains OS data © Crown copyright and database right 2024.
- Ordnance Survey (2026). OS OpenMap – Local, April 2026, buildings. Open Government Licence v3.0. Contains OS data © Crown copyright and database right 2026.
- The lidar classifier's training data, through OpenTopography: Auckland, New Zealand 2013, https://doi.org/10.5069/G9KW5CZ5 (CC BY 3.0 NZ; © Auckland Council 2016); Northland Regional Council and Toitū Te Whenua Land Information New Zealand (2022), Northland, New Zealand 2018–2020, collected by RPS Group, https://doi.org/10.5069/G9BR8QDQ (CC BY 4.0); Environment Canterbury Regional Council and Toitū Te Whenua Land Information New Zealand (2023), Kaikōura and Waimakariri, Canterbury, New Zealand 2022, collected by Aerial Surveys, https://doi.org/10.5069/G9Z60M78 (CC BY 4.0).
- Bus shelter height: Procity, square post bus shelter, technical features (total height 2,548 mm); States of Jersey Transport and Technical Services (2013), drawing 2013/11 rev. P2, and Andrew Harvey Architects for States of Jersey Property Holdings (2018), drawing 1310/06/01 rev. A (2,500 mm high).
- Redway width: Milton Keynes City Council (2024), Formal consultation report: Tudor Gardens, Calverton End proposed Redway link, citing the Milton Keynes Design Guide for Redways (at least 3 m wide).

### Software

- UMEP Developers (2026). solweig 0.1.0b96: High-performance SOLWEIG urban microclimate model (Rust + Python). https://pypi.org/project/solweig/0.1.0b96/ (GPL-3.0).
- UMEP Developers. UMEP-processing 3.0.3 (commit a7798db): functions/SOLWEIGpython/UTCI_calculations.py, whose UTCI polynomial `src/utci_final.py` reads at run time; not included here (GPL-3.0). https://github.com/UMEP-dev/UMEP-processing
- MapLibre GL JS 4.7.1 and PMTiles 3.2.1 (BSD-3-Clause); tippecanoe (BSD-2-Clause); Instrument Sans (SIL Open Font License 1.1). Licence texts in `licences/`.
