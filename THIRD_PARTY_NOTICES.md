# Third-Party Data Sources & Open Licenses (`THIRD_PARTY_NOTICES.md`)

All planetary datasets, mission telemetry, and engineering constraint documents consumed by **MarsWalk** are open scientific resources. Every data element in `public_packs/jezero/v1/` references its upstream source identifier (`source_id`) in [`public_packs/jezero/v1/manifest.json`](public_packs/jezero/v1/manifest.json).

---

## 1. NASA, JPL-Caltech, USGS & University of Arizona (Public Domain — 17 U.S.C. § 105)

1. **`SRC-M20-WAYPOINTS` & `SRC-M20-TRAVERSE` — Mars 2020 Perseverance MMGIS Waypoints & Traverse**
   - **Provider:** NASA / JPL-Caltech Mars 2020 Mission Operations
   - **URLs:**
     - `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json`
     - `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json`
   - **License:** Public Domain (17 U.S.C. § 105 — US Government Work)

2. **`SRC-TREK-HIRISE-25CM` & `SRC-USGS-HIRISE-DTM-1M` — Mars 2020 Terrain Relative Navigation HiRISE Orthomosaic (25 cm) & DTM (1 m)**
   - **Provider:** NASA Solar System Treks (SSERVI / JPL) & USGS Astrogeology Science Center / University of Arizona
   - **Citation:** Fergason, R. L., Hare, T. M., Mayer, D. P., Galuszka, D. M., Redding, B. L., Smith, E. D., Shinaman, J. R., Cheng, Y., & Otero, R. E. (2020). *Mars 2020 Terrain Relative Navigation Flight Product Generation: Digital Terrain Model and Orthorectified Mosaic*. 51st Lunar and Planetary Science Conference, Abstract #2020.
   - **URLs:**
     - `https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars`
     - `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif`
   - **License:** Public Domain (17 U.S.C. § 105)

3. **`SRC-USGS-SIM3464` — USGS SIM 3464 Geologic Map of the Jezero Crater Landing Site**
   - **Provider:** U.S. Geological Survey (USGS)
   - **Citation:** Sun, V. Z., & Stack, K. M. (2020). *Geologic map of Jezero crater and the Nili Planum region, Mars*: U.S. Geological Survey Scientific Investigations Map 3464, pamphlet 14 p., 1 sheet, scale 1:75,000, `https://doi.org/10.3133/sim3464`.
   - **URL:** `https://pubs.usgs.gov/sim/3464/sim3464_database.zip`
   - **License:** Public Domain (17 U.S.C. § 105)

4. **`SRC-NASA-XEVA` — NASA Extravehicular Activity (xEVA) System Concept of Operations (`EVA-EXP-0042` Rev B)**
   - **Provider:** National Aeronautics and Space Administration (NASA)
   - **URL:** `https://www.nasa.gov/wp-content/uploads/2017/02/eva-exp-0042_xeva_system_con_ops_rev_b_final_dtd_10192020_ref_doc.pdf`
   - **License:** Public Domain (17 U.S.C. § 105)

5. **`SRC-JPL-TRAVERSABILITY` — JPL Data-Driven Surface Traversability Analysis for Mars 2020**
   - **Provider:** Jet Propulsion Laboratory, California Institute of Technology
   - **Citation:** Ono, M., Rothrock, B., Iwashita, Y., et al. (2016). *Data-driven surface traversability analysis for Mars 2020 landing site selection*. IEEE Aerospace Conference.
   - **URL:** `https://www-robotics.jpl.nasa.gov/media/documents/Data-driven%20surface%20traversability%20analysis%20for%20Mars%202020%20landing%20site%20selection.pdf`
   - **License:** Public Use / IEEE Open Preprint via JPL Robotics

6. **`SRC-RAD-GALE` — MSL Curiosity Radiation Assessment Detector (RAD) Surface Dose Measurements**
   - **Provider:** Southwest Research Institute (SwRI) / NASA MSL Science Team
   - **Citation:** Hassler, D. M., Zeitlin, C., Wimmer-Schweingruber, R. F., et al. (2014). *Mars' Surface Radiation Environment Measured with the Mars Science Laboratory's Curiosity Rover*. Science, 343(6169), 1244797.
   - **URL:** `https://www.swri.org/newsroom/press-releases/swri-scientists-publish-first-radiation-measurements-the-surface-of-mars`
   - **License:** Open Scientific Citation (Scalar Reference Value `0.67 mSv/day`)

7. **`SRC-APOLLO-SLOPE` — Historical Apollo Lunar EVA Slope & Elevation Envelope**
   - **Citation:** Iqbal, Z., et al. (2024). *Acta Astronautica*.
   - **URL:** `https://www.sciencedirect.com/science/article/pii/S0094576524003746`
   - **License:** Open Access Citation

---

## 2. Canadian Space Agency (CSA) & Open Government Licence – Canada

Contains information licensed under the **Open Government Licence – Canada**.
Full license terms: [https://open.canada.ca/en/open-government-licence-canada](https://open.canada.ca/en/open-government-licence-canada)
