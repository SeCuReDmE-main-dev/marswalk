import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Layers, Minus, Plus, Compass, RotateCcw } from "lucide-react";
import type {
  MarswalkData,
  HazardCell,
  EvaRouteFeature,
  Waypoint,
} from "./data/types";
import {
  cellAt,
  cellBounds,
  distanceMeters,
  linePoints,
  numericBbox,
  routeParts,
  type Bbox,
} from "./domain";

export interface LayerState {
  imagery: boolean;
  hazards: boolean;
  rover: boolean;
  stops: boolean;
  opacity: number;
}
interface Props {
  data: MarswalkData;
  cell?: HazardCell;
  stop?: EvaRouteFeature;
  waypoint?: Waypoint;
  layers: LayerState;
  onLayers: (layers: LayerState) => void;
  onCell: (cell?: HazardCell) => void;
  onStop: (stop: EvaRouteFeature) => void;
  onWaypoint: (point: Waypoint) => void;
  fit: "route" | "coverage";
  fitTick: number;
}
const colors = { GO: "#67ad99", CAUTION: "#edaa4d", NO_GO: "#df6658" };
const latLngBounds = (b: Bbox): L.LatLngBoundsExpression => [
  [b[1], b[0]],
  [b[3], b[2]],
];

// A local, explicitly coarse backdrop from actual pack elevations. Never a generated
// satellite photo: NASA imagery is a separately toggled/attributed remote tile layer.
function elevationImage(data: MarswalkData) {
  const { rows, cols, cells } = data.hazards,
    canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d")!;
  const values = cells.map((c) => c.elev_m.value),
    low = Math.min(...values),
    high = Math.max(...values);
  cells.forEach((c) => {
    const t = (c.elev_m.value - low) / Math.max(1, high - low);
    ctx.fillStyle = `rgb(${Math.round(71 + t * 77)},${Math.round(55 + t * 47)},${Math.round(48 + t * 31)})`;
    ctx.fillRect(c.col, c.row, 1, 1);
  });
  return canvas.toDataURL();
}
export default function MapView(props: Props) {
  const el = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | undefined>(undefined),
    callbacks = useRef(props);
  callbacks.current = props;
  const groups = useRef<
    | {
        hazards: L.LayerGroup;
        rover: L.LayerGroup;
        stops: L.LayerGroup;
        selection: L.LayerGroup;
        tiles?: L.TileLayer;
      }
    | undefined
  >(undefined);
  const cells = useRef(new Map<string, L.Rectangle>());
  const [layerPanel, setLayerPanel] = useState(false),
    [tileState, setTileState] = useState<"loading" | "loaded" | "error">(
      "loading",
    ),
    [cursor, setCursor] = useState("Planetocentric east · Mars sphere");
  useEffect(() => {
    if (!el.current) return;
    const data = props.data,
      crs = {
        ...L.CRS.EPSG4326,
        distance: (a: L.LatLng, b: L.LatLng) =>
          distanceMeters([a.lng, a.lat], [b.lng, b.lat]),
      };
    const m = L.map(el.current, {
      crs,
      zoomControl: false,
      attributionControl: true,
      minZoom: 5,
      maxZoom: 18,
      zoomSnap: 0.5,
      preferCanvas: false,
    });
    map.current = m;
    m.attributionControl.setPrefix(false);
    L.control
      .scale({ imperial: false, position: "bottomleft", maxWidth: 150 })
      .addTo(m);
    const bounds = numericBbox(data.hazards.bbox);
    m.createPane("elevationBackdrop");
    m.getPane("elevationBackdrop")!.style.zIndex = "190";
    L.imageOverlay(elevationImage(data), latLngBounds(bounds), {
      pane: "elevationBackdrop",
      opacity: 1,
      interactive: false,
      attribution: "Coarse elevation: USGS HiRISE DTM · DERIVED",
    }).addTo(m);
    const tileSpec = data.manifest.basemaps[0];
    let tiles: L.TileLayer | undefined;
    if (tileSpec?.tile_grid === "geographic_2to1_256px") {
      tiles = L.tileLayer(
        tileSpec.template_url.replace("{row}", "{y}").replace("{col}", "{x}"),
        {
          minZoom: tileSpec.min_zoom,
          maxNativeZoom: tileSpec.max_zoom,
          maxZoom: 18,
          bounds: latLngBounds(numericBbox(tileSpec.bbox)),
          noWrap: true,
          attribution: "Imagery: NASA/JPL-Caltech · USGS · HiRISE",
        },
      );
      tiles.on("tileload", () => setTileState("loaded"));
      tiles.on("tileerror", () =>
        setTileState((s) => (s === "loaded" ? s : "error")),
      );
      if (callbacks.current.layers.imagery) tiles.addTo(m);
    } else setTileState("error");
    const hazards = L.layerGroup(),
      rover = L.layerGroup(),
      stops = L.layerGroup(),
      selection = L.layerGroup().addTo(m);
    for (const c of data.hazards.cells) {
      const rectangle = L.rectangle(latLngBounds(cellBounds(data.hazards, c)), {
        color: colors[c.verdict],
        weight: 0.5,
        fillColor: colors[c.verdict],
        fillOpacity: callbacks.current.layers.opacity,
        opacity: 0.32,
      });
      rectangle.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        callbacks.current.onCell(c);
      });
      rectangle.bindTooltip(`${c.cell_id} · ${c.verdict}`, {
        sticky: true,
        direction: "top",
      });
      hazards.addLayer(rectangle);
      cells.current.set(c.cell_id, rectangle);
    }
    L.rectangle(latLngBounds(bounds), {
      color: "#eaded0",
      weight: 1.5,
      dashArray: "6 6",
      fill: false,
      interactive: false,
    }).addTo(m);
    const parts = routeParts(data);
    for (const f of parts.traverse)
      L.polyline(
        linePoints(f).map((p) => [p[1], p[0]] as L.LatLngTuple),
        {
          color: "#b9c5ce",
          weight: 2,
          dashArray: "4 6",
          opacity: 0.7,
          interactive: false,
        },
      ).addTo(rover);
    for (const w of data.waypoints.features) {
      const point = L.circleMarker([w.properties.lat, w.properties.lon], {
        radius: 3,
        color: "#b6d8e6",
        weight: 1,
        fillOpacity: 0.7,
      });
      point.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        callbacks.current.onWaypoint(w);
      });
      rover.addLayer(point);
    }
    if (parts.candidate) {
      const points = linePoints(parts.candidate).map(
        (p) => [p[1], p[0]] as L.LatLngTuple,
      );
      L.polyline(points, {
        color: "#102b3d",
        weight: 8,
        opacity: 0.9,
        interactive: false,
      }).addTo(m);
      L.polyline(points, {
        color: "#4fd7eb",
        weight: 4,
        opacity: 1,
        interactive: false,
      }).addTo(m);
    }
    parts.stops.forEach((s, i) => {
      if (s.geometry.type !== "Point") return;
      const [lon, lat] = s.geometry.coordinates.map(Number);
      const marker = L.marker([lat, lon], {
        icon: L.divIcon({
          className: "stop-marker",
          html: `<span>${i + 1}</span>`,
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
        title: `Science stop ${i + 1}: ${s.properties.title}`,
        keyboard: true,
      });
      marker.on("add", () =>
        marker
          .getElement()
          ?.setAttribute(
            "aria-label",
            `Science stop ${i + 1}: ${s.properties.title}`,
          ),
      );
      marker.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        callbacks.current.onStop(s);
      });
      stops.addLayer(marker);
    });
    groups.current = { hazards, rover, stops, selection, tiles };
    for (const [key, group] of Object.entries({ hazards, rover, stops }))
      if (callbacks.current.layers[key as "hazards" | "rover" | "stops"])
        group.addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) =>
      callbacks.current.onCell(
        cellAt(data.hazards, [e.latlng.lng, e.latlng.lat]),
      ),
    );
    m.on("mousemove", (e: L.LeafletMouseEvent) =>
      setCursor(`${e.latlng.lat.toFixed(4)}° N  ${e.latlng.lng.toFixed(4)}° E`),
    );
    const route = parts.candidate ? linePoints(parts.candidate) : [];
    m.fitBounds(
      route.length
        ? L.latLngBounds(route.map((p) => [p[1], p[0]] as L.LatLngTuple))
        : latLngBounds(bounds),
      { padding: [60, 60], maxZoom: 15 },
    );
    const observer = new ResizeObserver(() => m.invalidateSize());
    observer.observe(el.current);
    return () => {
      observer.disconnect();
      m.remove();
      map.current = undefined;
      groups.current = undefined;
      cells.current.clear();
    };
  }, [props.data]);
  useEffect(() => {
    const m = map.current,
      g = groups.current;
    if (!m || !g) return;
    for (const key of ["hazards", "rover", "stops"] as const) {
      if (props.layers[key]) g[key].addTo(m);
      else m.removeLayer(g[key]);
    }
    if (g.tiles) {
      if (props.layers.imagery) g.tiles.addTo(m);
      else m.removeLayer(g.tiles);
    }
    cells.current.forEach((r, id) =>
      r.setStyle({
        fillOpacity: props.layers.opacity,
        color:
          props.cell?.cell_id === id
            ? "#fff"
            : colors[
                props.data.hazards.cells.find((c) => c.cell_id === id)!.verdict
              ],
        weight: props.cell?.cell_id === id ? 3 : 0.5,
        opacity: props.cell?.cell_id === id ? 1 : 0.32,
      }),
    );
  }, [props.layers, props.cell, props.data]);
  useEffect(() => {
    const m = map.current,
      g = groups.current;
    if (!m || !g) return;
    g.selection.clearLayers();
    const point = props.waypoint
      ? [props.waypoint.properties.lon, props.waypoint.properties.lat]
      : props.stop?.geometry.type === "Point"
        ? props.stop.geometry.coordinates.map(Number)
        : props.cell
          ? [props.cell.lon, props.cell.lat]
          : undefined;
    if (point) {
      const ll: L.LatLngTuple = [point[1], point[0]];
      L.circleMarker(ll, {
        radius: props.cell ? 8 : 21,
        color: "#fff",
        fill: false,
        weight: 2,
        interactive: false,
      }).addTo(g.selection);
      if (!m.getBounds().pad(-0.12).contains(ll))
        m.panTo(ll, {
          animate: !matchMedia("(prefers-reduced-motion: reduce)").matches,
        });
    }
  }, [props.stop, props.cell, props.waypoint]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const route = routeParts(props.data).candidate;
    const pts = route ? linePoints(route) : [];
    m.fitBounds(
      props.fit === "route" && pts.length
        ? L.latLngBounds(pts.map((p) => [p[1], p[0]] as L.LatLngTuple))
        : latLngBounds(numericBbox(props.data.hazards.bbox)),
      { padding: [42, 42], maxZoom: 16, animate: false },
    );
  }, [props.fitTick, props.fit, props.data]);
  return (
    <section className="map-workspace" aria-label="Jezero terrain workspace">
      <div
        ref={el}
        className="map-canvas"
        aria-label="Interactive map of Jezero. Use the guide lists to select terrain and stops with the keyboard."
      />
      <div className="map-top-controls">
        <button
          className="map-button"
          aria-expanded={layerPanel}
          onClick={() => setLayerPanel(!layerPanel)}
        >
          <Layers size={17} /> Layers <span>{layerPanel ? "−" : "+"}</span>
        </button>
        {layerPanel && (
          <div className="layer-menu">
            {(["imagery", "hazards", "rover", "stops"] as const).map((key) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={props.layers[key]}
                  onChange={(e) =>
                    props.onLayers({ ...props.layers, [key]: e.target.checked })
                  }
                />
                {
                  {
                    imagery: "NASA imagery",
                    hazards: "Terrain assessments",
                    rover: "Perseverance traverse",
                    stops: "Science stops",
                  }[key]
                }
              </label>
            ))}
            <label className="opacity-label">
              Hazard opacity{" "}
              <output>{Math.round(props.layers.opacity * 100)}%</output>
              <input
                type="range"
                min="0"
                max="0.8"
                step="0.05"
                value={props.layers.opacity}
                onChange={(e) =>
                  props.onLayers({
                    ...props.layers,
                    opacity: Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
        )}
      </div>
      <div className="map-coverage-note">
        <span className="coverage-dot" /> Assessed window · outside: not
        assessed
      </div>
      <div className="map-north" title="North">
        <Compass size={24} />
        <span>N</span>
      </div>
      <div className="map-zoom">
        <button aria-label="Zoom in" onClick={() => map.current?.zoomIn()}>
          <Plus size={20} />
        </button>
        <button aria-label="Zoom out" onClick={() => map.current?.zoomOut()}>
          <Minus size={20} />
        </button>
      </div>
      <div className="map-legend">
        <b>Map key</b>
        <span>
          <i className="legend-line" /> Candidate walk <small>SIMULATED</small>
        </span>
        <span>
          <i className="legend-line rover" /> Rover traverse{" "}
          <small>MEASURED</small>
        </span>
        <div className="legend-verdicts">
          {Object.entries(colors).map(([key, color]) => (
            <span key={key}>
              <i style={{ background: color }} />
              {key}
            </span>
          ))}
        </div>
      </div>
      <div className="map-coordinate">{cursor}</div>
      <div className="imagery-note">
        {props.layers.imagery
          ? tileState === "loaded"
            ? "NASA HiRISE imagery"
            : tileState === "error"
              ? "Imagery unavailable · coarse elevation remains visible"
              : "Loading NASA imagery · coarse elevation backdrop"
          : "Coarse elevation backdrop · DERIVED"}
        {tileState === "error" && props.layers.imagery && (
          <button
            aria-label="Retry NASA imagery"
            onClick={() => {
              setTileState("loading");
              groups.current?.tiles?.redraw();
            }}
          >
            <RotateCcw size={13} />
          </button>
        )}
      </div>
    </section>
  );
}
