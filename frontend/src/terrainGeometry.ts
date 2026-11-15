import { MARS_RADIUS_M, contains, numericBbox, type LonLat } from "./domain";
import type { HazardGrid } from "./data/types";

export function createTerrainGeometry(grid: HazardGrid) {
  const bbox = numericBbox(grid.bbox);
  const center: LonLat = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
  const rad = Math.PI / 180,
    stepX = MARS_RADIUS_M * rad * Math.cos(center[1] * rad),
    stepY = MARS_RADIUS_M * rad;
  const span = Math.max(
    (bbox[2] - bbox[0]) * stepX,
    (bbox[3] - bbox[1]) * stepY,
  );
  const scale = 2 / span;
  const min = Math.min(...grid.cells.map((c) => c.elev_m.value)),
    max = Math.max(...grid.cells.map((c) => c.elev_m.value));
  const byId = new Map(grid.cells.map((c, i) => [`${c.row}:${c.col}`, i]));
  const vertices = grid.cells.map((c) => ({
    x: (c.lon - center[0]) * stepX * scale,
    y: (c.elev_m.value - min) * scale,
    z: -(c.lat - center[1]) * stepY * scale,
    cell: c,
  }));
  const faces: [number, number, number][] = [];
  for (let row = 0; row < grid.rows - 1; row++)
    for (let col = 0; col < grid.cols - 1; col++) {
      const ids = [
        byId.get(`${row}:${col}`),
        byId.get(`${row}:${col + 1}`),
        byId.get(`${row + 1}:${col}`),
        byId.get(`${row + 1}:${col + 1}`),
      ];
      if (ids.some((i) => i === undefined)) continue;
      const [a, b, c, d] = ids as number[];
      faces.push([a, b, c], [b, d, c]);
    }
  function locate(point: LonLat) {
    if (!contains(bbox, point)) return undefined;
    const col = Math.min(
      grid.cols - 1,
      Math.max(
        0,
        Math.floor(((point[0] - bbox[0]) / (bbox[2] - bbox[0])) * grid.cols),
      ),
    );
    const row = Math.min(
      grid.rows - 1,
      Math.max(
        0,
        Math.floor(((bbox[3] - point[1]) / (bbox[3] - bbox[1])) * grid.rows),
      ),
    );
    const index = byId.get(`${row}:${col}`);
    if (index === undefined) return undefined;
    // Route/marker height is display interpolation, never a new physical assessment.
    const u = Math.min(
      grid.cols - 1,
      Math.max(
        0,
        ((point[0] - bbox[0]) / (bbox[2] - bbox[0])) * grid.cols - 0.5,
      ),
    );
    const v = Math.min(
      grid.rows - 1,
      Math.max(
        0,
        ((bbox[3] - point[1]) / (bbox[3] - bbox[1])) * grid.rows - 0.5,
      ),
    );
    const c0 = Math.floor(u),
      r0 = Math.floor(v),
      c1 = Math.min(grid.cols - 1, c0 + 1),
      r1 = Math.min(grid.rows - 1, r0 + 1);
    const height = (r: number, c: number) =>
      vertices[byId.get(`${r}:${c}`) ?? index].y;
    const top = height(r0, c0) * (1 - (u - c0)) + height(r0, c1) * (u - c0);
    const bottom = height(r1, c0) * (1 - (u - c0)) + height(r1, c1) * (u - c0);
    return {
      x: (point[0] - center[0]) * stepX * scale,
      z: -(point[1] - center[1]) * stepY * scale,
      y: top * (1 - (v - r0)) + bottom * (v - r0),
    };
  }
  return { vertices, faces, min, max, span, scale, center, locate, bbox };
}

// NASA Mars Trek geographic WMTS has 2^(z+1) columns and 2^z rows.
export function geographicTilePixel([lon, lat]: LonLat, z: number) {
  return {
    x: ((lon + 180) / 360) * 2 ** (z + 1) * 256,
    y: ((90 - lat) / 180) * 2 ** z * 256,
  };
}
