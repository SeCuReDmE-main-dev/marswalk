import { useEffect, useMemo, useRef, useState } from "react";
import {
  Maximize,
  Minus,
  Plus,
  RotateCcw,
  Settings2,
  Play,
  Pause,
} from "lucide-react";
import type { MarswalkData, HazardCell } from "./data/types";
import type { RouteOverlay } from "./EngineTools";
import { linePoints, routeParts, type LonLat } from "./domain";
import { createTerrainGeometry, geographicTilePixel } from "./terrainGeometry";
import type { PreviewPosition } from "./routePreview";

type Mode = "relief" | "hazards" | "satellite";
const verdictColors = { GO: "#67ad99", CAUTION: "#edaa4d", NO_GO: "#df6658" };
const initialCamera = { yaw: -0.65, pitch: 0.92, zoom: 0.82 };
export default function Terrain3D({
  data,
  cell,
  onCell,
  plannedRoute,
  picking,
  onPick,
  previewPosition,
}: {
  data: MarswalkData;
  cell?: HazardCell;
  onCell: (c: HazardCell) => void;
  plannedRoute?: RouteOverlay;
  picking: boolean;
  onPick: (p: LonLat) => void;
  previewPosition?: PreviewPosition;
}) {
  const model = useMemo(() => createTerrainGeometry(data.hazards), [data]);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [camera, setCamera] = useState(initialCamera),
    [mode, setMode] = useState<Mode>("satellite"),
    [exaggeration, setExaggeration] = useState(1);
  const [wireframe, setWireframe] = useState(false),
    [orbit, setOrbit] = useState(false),
    [settings, setSettings] = useState(false);
  const [texture, setTexture] = useState<HTMLCanvasElement>(),
    [textureStatus, setTextureStatus] = useState<
      "idle" | "loading" | "loaded" | "error"
    >("idle");
  const [reduceMotion, setReduceMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const pointer = useRef<
    | {
        x: number;
        y: number;
        startX: number;
        startY: number;
        id: number;
        dragged: boolean;
      }
    | undefined
  >(undefined);
  const projected = useRef<{ x: number; y: number; depth: number }[]>([]);
  const { candidate, stops } = routeParts(data);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ width: r.width, height: r.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => {
      setReduceMotion(media.matches);
      if (media.matches) setOrbit(false);
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!orbit || reduceMotion) return;
    let frame = 0,
      last = 0;
    function tick(time: number) {
      if (last) {
        const dt = Math.min(50, time - last);
        setCamera((c) => ({ ...c, yaw: c.yaw + dt * 0.000075 }));
      }
      last = time;
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [orbit, reduceMotion]);
  useEffect(() => {
    if (mode !== "satellite" || texture) return;
    const spec = data.manifest.basemaps.find(
      (b) => b.tile_grid === "geographic_2to1_256px",
    );
    if (!spec) {
      setTextureStatus("error");
      return;
    }
    let disposed = false;
    const images: HTMLImageElement[] = [];
    const timer = setTimeout(() => {
      if (!disposed) setTextureStatus("error");
    }, 15000);
    setTextureStatus("loading");
    const z = Math.min(13, spec.max_zoom ?? 13),
      a = geographicTilePixel([model.bbox[0], model.bbox[3]], z),
      b = geographicTilePixel([model.bbox[2], model.bbox[1]], z);
    const out = document.createElement("canvas");
    out.width = 768;
    out.height = 768;
    const ctx = out.getContext("2d")!;
    const requests: Promise<void>[] = [];
    for (let row = Math.floor(a.y / 256); row <= Math.floor(b.y / 256); row++)
      for (
        let col = Math.floor(a.x / 256);
        col <= Math.floor(b.x / 256);
        col++
      ) {
        requests.push(
          new Promise((resolve, reject) => {
            const img = new Image();
            images.push(img);
            img.crossOrigin = "anonymous";
            img.onload = () => {
              if (!disposed)
                ctx.drawImage(
                  img,
                  ((col * 256 - a.x) / (b.x - a.x)) * 768,
                  ((row * 256 - a.y) / (b.y - a.y)) * 768,
                  (256 / (b.x - a.x)) * 768,
                  (256 / (b.y - a.y)) * 768,
                );
              resolve();
            };
            img.onerror = reject;
            img.src = spec.template_url
              .replace("{z}", String(z))
              .replace("{row}", String(row))
              .replace("{col}", String(col));
          }),
        );
      }
    Promise.all(requests)
      .then(() => {
        if (disposed) return;
        clearTimeout(timer);
        setTexture(out);
        setTextureStatus("loaded");
      })
      .catch(() => {
        if (!disposed) {
          clearTimeout(timer);
          setTextureStatus("error");
        }
      });
    return () => {
      disposed = true;
      clearTimeout(timer);
      images.forEach((img) => {
        img.onload = null;
        img.onerror = null;
        img.src = "";
      });
    };
  }, [mode, texture, data, model]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || size.width < 1 || size.height < 1) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    element.width = Math.round(size.width * dpr);
    element.height = Math.round(size.height * dpr);
    const ctx = element.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    const { width: w, height: h } = size;
    const bg = ctx.createRadialGradient(
      w * 0.5,
      h * 0.45,
      0,
      w * 0.5,
      h * 0.5,
      Math.max(w, h) * 0.75,
    );
    bg.addColorStop(0, "#294351");
    bg.addColorStop(1, "#0b1823");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#b1c6ce35";
    for (let i = 0; i < 65; i++) {
      const x = (((i * 137.508) % 997) / 997) * w,
        y = (((i * 71.713) % 991) / 991) * h;
      ctx.fillRect(x, y, 1, 1);
    }
    const cy = Math.cos(camera.yaw),
      sy = Math.sin(camera.yaw),
      cp = Math.cos(camera.pitch),
      sp = Math.sin(camera.pitch),
      focal = Math.min(w, h) * 1.52 * camera.zoom;
    const middle = ((model.max - model.min) * model.scale * exaggeration) / 2;
    function project(p: { x: number; y: number; z: number }, lift = 0) {
      const rx = cy * p.x - sy * p.z,
        rz = sy * p.x + cy * p.z,
        ry = p.y * exaggeration - middle + lift;
      const vertical = cp * ry - sp * rz,
        depth = sp * ry + cp * rz;
      const factor = focal / Math.max(0.8, 4 - depth);
      return { x: w / 2 + rx * factor, y: h * 0.52 - vertical * factor, depth };
    }
    const points = model.vertices.map((p) => project(p));
    projected.current = points;
    // Painter's algorithm projects the actual grid; it never calculates a safety verdict.
    const faces = model.faces
      .map((ids) => ({
        ids,
        depth: ids.reduce((sum, i) => sum + points[i].depth, 0) / 3,
      }))
      .sort((a, b) => a.depth - b.depth);
    for (const { ids } of faces) {
      const [a, b, c] = ids.map((i) => points[i]),
        [pa, pb, pc] = ids.map((i) => model.vertices[i]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.lineTo(c.x, c.y);
      ctx.closePath();
      const ux = pb.x - pa.x,
        uy = (pb.y - pa.y) * exaggeration,
        uz = pb.z - pa.z,
        vx = pc.x - pa.x,
        vy = (pc.y - pa.y) * exaggeration,
        vz = pc.z - pa.z;
      let nx = uy * vz - uz * vy,
        ny = uz * vx - ux * vz,
        nz = ux * vy - uy * vx;
      const length = Math.hypot(nx, ny, nz) || 1;
      if (ny < 0) {
        nx = -nx;
        ny = -ny;
        nz = -nz;
      }
      const light =
        0.45 + 0.55 * Math.max(0, (nx * -0.4 + ny * 0.8 + nz * 0.45) / length);
      if (mode === "satellite" && texture) {
        const uv = ids.map((i) => {
          const c = model.vertices[i].cell;
          return {
            x:
              ((c.lon - model.bbox[0]) / (model.bbox[2] - model.bbox[0])) *
              texture.width,
            y:
              ((model.bbox[3] - c.lat) / (model.bbox[3] - model.bbox[1])) *
              texture.height,
          };
        });
        const [u, v, t] = uv;
        const det = u.x * (v.y - t.y) + v.x * (t.y - u.y) + t.x * (u.y - v.y);
        if (Math.abs(det) > 1e-8) {
          const affine = (p: number, q: number, r: number) => [
            (p * (v.y - t.y) + q * (t.y - u.y) + r * (u.y - v.y)) / det,
            (p * (t.x - v.x) + q * (u.x - t.x) + r * (v.x - u.x)) / det,
            (p * (v.x * t.y - t.x * v.y) +
              q * (t.x * u.y - u.x * t.y) +
              r * (u.x * v.y - v.x * u.y)) /
              det,
          ];
          const ax = affine(a.x, b.x, c.x),
            ay = affine(a.y, b.y, c.y);
          ctx.save();
          ctx.clip();
          ctx.transform(ax[0], ay[0], ax[1], ay[1], ax[2], ay[2]);
          ctx.drawImage(texture, 0, 0);
          ctx.restore();
          ctx.fillStyle = `rgba(7,15,20,${(1 - light) * 0.45})`;
          ctx.fill();
        }
      } else {
        const rel =
          (pa.y + pb.y + pc.y) /
          3 /
          Math.max(0.001, (model.max - model.min) * model.scale);
        if (mode === "hazards") ctx.fillStyle = verdictColors[pa.cell.verdict];
        else
          ctx.fillStyle = `rgb(${Math.round((105 + rel * 95) * light)},${Math.round((67 + rel * 74) * light)},${Math.round((48 + rel * 55) * light)})`;
        ctx.fill();
        ctx.strokeStyle = ctx.fillStyle;
        ctx.lineWidth = 0.45;
        ctx.stroke();
      }
      if (wireframe) {
        ctx.strokeStyle = "#d0e8ed38";
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
    const route =
      plannedRoute?.coordinates || (candidate ? linePoints(candidate) : []);
    ctx.strokeStyle = plannedRoute
      ? verdictColors[plannedRoute.verdict as keyof typeof verdictColors] ||
        "#4fd7eb"
      : "#4fd7eb";
    ctx.lineWidth = 2.8;
    ctx.lineCap = "round";
    ctx.shadowBlur = 8;
    ctx.shadowColor = ctx.strokeStyle;
    ctx.beginPath();
    let pen = false;
    for (const p of route) {
      const v = model.locate(p);
      if (!v) {
        pen = false;
        continue;
      }
      const s = project(v, 0.018);
      if (pen) ctx.lineTo(s.x, s.y);
      else ctx.moveTo(s.x, s.y);
      pen = true;
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
    stops.forEach((stop, i) => {
      if (stop.geometry.type !== "Point") return;
      const p = model.locate(stop.geometry.coordinates.map(Number) as LonLat);
      if (!p) return;
      const s = project(p, 0.035);
      ctx.beginPath();
      ctx.arc(s.x, s.y, 10, 0, 2 * Math.PI);
      ctx.fillStyle = "#143645";
      ctx.fill();
      ctx.strokeStyle = "#bef4fa";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "bold 10px Segoe UI";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "white";
      ctx.fillText(String(i + 1), s.x, s.y);
    });
    if (previewPosition) {
      const v = model.locate(previewPosition.point);
      if (v) {
        const s = project(v, 0.04);
        ctx.beginPath();
        ctx.arc(s.x, s.y, 15, 0, 2 * Math.PI);
        ctx.fillStyle = "#e9763d40";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(s.x, s.y, 7, 0, 2 * Math.PI);
        ctx.fillStyle = "#cf602f";
        ctx.fill();
        ctx.strokeStyle = "white";
        ctx.lineWidth = 2.5;
        ctx.stroke();
        ctx.font = "bold 10px Segoe UI";
        ctx.textAlign = "center";
        ctx.fillStyle = "#fff";
        ctx.fillText("PREVIEW", s.x, s.y - 24);
      }
    }
    if (cell) {
      const v = model.locate([cell.lon, cell.lat]);
      if (v) {
        const s = project(v, 0.035);
        ctx.beginPath();
        ctx.arc(s.x, s.y, 7, 0, 2 * Math.PI);
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.font = "11px Segoe UI";
        ctx.fillStyle = "white";
        ctx.textAlign = "center";
        ctx.fillText(cell.cell_id, s.x, s.y - 17);
      }
    }
    const north = project({ x: 0, y: 0, z: -0.45 }),
      origin = project({ x: 0, y: 0, z: 0 });
    const dx = north.x - origin.x,
      dy = north.y - origin.y,
      len = Math.hypot(dx, dy) || 1;
    const ax = w - 39,
      ay = h - 90;
    ctx.strokeStyle = "#a5d8e4";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(ax + (dx / len) * 22, ay + (dy / len) * 22);
    ctx.stroke();
    ctx.fillStyle = "#d0e8ed";
    ctx.font = "11px Segoe UI";
    ctx.fillText("N", ax + (dx / len) * 31, ay + (dy / len) * 31);
  }, [
    model,
    size,
    camera,
    mode,
    exaggeration,
    wireframe,
    texture,
    cell,
    candidate,
    stops,
    plannedRoute,
    previewPosition,
  ]);

  function changeZoom(delta: number) {
    setCamera((c) => ({
      ...c,
      zoom: Math.min(2.1, Math.max(0.55, c.zoom + delta)),
    }));
  }
  return (
    <section className="terrain-view" aria-label="3D Jezero terrain preview">
      <canvas
        ref={canvas}
        tabIndex={0}
        role="img"
        aria-label={`Interactive 3D terrain from ${data.hazards.cells.length} derived elevation samples. Drag to orbit, use arrow keys to rotate, plus or minus to zoom. Select a model sample to inspect its supplied assessment.`}
        onPointerDown={(e) => {
          pointer.current = {
            x: e.clientX,
            y: e.clientY,
            startX: e.clientX,
            startY: e.clientY,
            id: e.pointerId,
            dragged: false,
          };
          e.currentTarget.setPointerCapture(e.pointerId);
          setOrbit(false);
        }}
        onPointerMove={(e) => {
          const p = pointer.current;
          if (!p || p.id !== e.pointerId) return;
          const dx = e.clientX - p.x,
            dy = e.clientY - p.y;
          if (Math.hypot(e.clientX - p.startX, e.clientY - p.startY) > 5)
            p.dragged = true;
          p.x = e.clientX;
          p.y = e.clientY;
          if (p.dragged)
            setCamera((c) => ({
              ...c,
              yaw: c.yaw + dx * 0.008,
              pitch: Math.max(0.2, Math.min(1.5, c.pitch + dy * 0.006)),
            }));
        }}
        onPointerUp={(e) => {
          const p = pointer.current;
          pointer.current = undefined;
          if (!p || p.dragged) return;
          const r = e.currentTarget.getBoundingClientRect();
          let best = -1,
            distance = 22;
          projected.current.forEach((s, i) => {
            const d = Math.hypot(
              s.x - (e.clientX - r.left),
              s.y - (e.clientY - r.top),
            );
            if (d < distance) {
              distance = d;
              best = i;
            }
          });
          if (best >= 0) {
            const c = model.vertices[best].cell;
            if (picking) onPick([c.lon, c.lat]);
            else onCell(c);
          }
        }}
        onPointerCancel={() => {
          pointer.current = undefined;
        }}
        onKeyDown={(e) => {
          if (
            [
              "ArrowLeft",
              "ArrowRight",
              "ArrowUp",
              "ArrowDown",
              "+",
              "=",
              "-",
              "Home",
            ].includes(e.key)
          ) {
            e.preventDefault();
            setOrbit(false);
            if (e.key === "Home") setCamera(initialCamera);
            else if (["+", "=", "-"].includes(e.key))
              changeZoom(e.key === "-" ? -0.1 : 0.1);
            else
              setCamera((c) => ({
                ...c,
                yaw:
                  c.yaw +
                  (e.key === "ArrowLeft"
                    ? -0.12
                    : e.key === "ArrowRight"
                      ? 0.12
                      : 0),
                pitch: Math.max(
                  0.2,
                  Math.min(
                    1.5,
                    c.pitch +
                      (e.key === "ArrowUp"
                        ? 0.1
                        : e.key === "ArrowDown"
                          ? -0.1
                          : 0),
                  ),
                ),
              }));
          }
        }}
      />
      <div className="terrain-heading">
        <span className="eyebrow">JEZERO, MARS</span>
        <h2>Jezero in 3D</h2>
        <span>
          DERIVED · {data.hazards.rows} × {data.hazards.cols} samples
        </span>
      </div>
      <button
        className="map-button terrain-settings-toggle"
        aria-expanded={settings}
        onClick={() => setSettings(!settings)}
      >
        <Settings2 size={15} />
        View settings
      </button>
      {settings && (
        <div className="terrain-settings">
          <label>
            Surface
            <select
              aria-label="3D surface style"
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
            >
              <option value="relief">Shaded terrain</option>
              <option value="hazards">Terrain assessments</option>
              <option value="satellite">NASA satellite imagery</option>
            </select>
          </label>
          <label>
            Stretch terrain height{" "}
            <output>
              {exaggeration.toLocaleString("en-US", {
                maximumFractionDigits: 2,
              })}
              ×
            </output>
            <input
              aria-label="Stretch terrain height"
              type="range"
              min="1"
              max="4"
              step="0.25"
              value={exaggeration}
              onChange={(e) => setExaggeration(Number(e.target.value))}
            />
          </label>
          <p>Display only; assessments do not change.</p>
          <label className="terrain-check">
            <input
              type="checkbox"
              checked={wireframe}
              onChange={(e) => setWireframe(e.target.checked)}
            />
            Show model grid
          </label>
          <label className="terrain-check">
            <input
              type="checkbox"
              checked={reduceMotion}
              onChange={(e) => {
                setReduceMotion(e.target.checked);
                if (e.target.checked) setOrbit(false);
              }}
            />
            Reduce motion
          </label>
          <p>
            Grid samples are approximately {data.hazards.cell_size_m.toFixed(0)}{" "}
            m apart. The shape between them is estimated.
          </p>
        </div>
      )}
      <div className="terrain-toolbar">
        <button
          className="map-button"
          onClick={() => {
            setCamera(initialCamera);
            setOrbit(false);
          }}
        >
          <RotateCcw size={14} />
          Reset view
        </button>
        <button
          className="map-button"
          onClick={() => {
            setOrbit(false);
            setCamera((c) => ({ ...c, pitch: 1.5 }));
          }}
        >
          <Maximize size={14} />
          Top view
        </button>
        <button
          className="map-button"
          disabled={reduceMotion}
          aria-pressed={orbit}
          onClick={() => setOrbit(!orbit)}
        >
          {orbit ? <Pause size={14} /> : <Play size={14} />}{" "}
          {orbit ? "Pause orbit" : "Orbit camera"}
        </button>
      </div>
      <div className="terrain-zoom">
        <button
          className="map-button"
          aria-label="Zoom into 3D terrain"
          onClick={() => changeZoom(0.1)}
        >
          <Plus size={18} />
        </button>
        <button
          className="map-button"
          aria-label="Zoom out of 3D terrain"
          onClick={() => changeZoom(-0.1)}
        >
          <Minus size={18} />
        </button>
      </div>
      <div className="terrain-caption">
        <b>
          {exaggeration === 1
            ? "True vertical scale"
            : `Height exaggerated ${exaggeration.toLocaleString("en-US", { maximumFractionDigits: 2 })}× · display only`}
        </b>
        <span>
          Drag to orbit · arrows rotate · click a sample to inspect
          {picking ? " · picks snap to sample centres" : ""}
        </span>
        <span>
          {mode === "satellite"
            ? textureStatus === "loaded"
              ? "NASA/JPL-Caltech · USGS · HiRISE imagery over coarse terrain"
              : textureStatus === "error"
                ? "NASA texture unavailable · shaded terrain remains"
                : "Loading NASA texture · shaded terrain remains"
            : "USGS HiRISE ground heights · DERIVED, estimated surface between samples"}
        </span>
      </div>
      {mode === "hazards" && (
        <div className="terrain-key">
          {Object.entries(verdictColors).map(([v, c]) => (
            <span key={v}>
              <i style={{ background: c }} />
              {v}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
