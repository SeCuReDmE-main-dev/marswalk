import type { MarswalkData } from "./data/types";

const layerNames: Record<string, string> = {
  themis_ti_100m: "Ground heating and cooling data",
  crism_mtrdr_18m: "Mineral observations from reflected light",
  meda_pds4_env: "Rover weather and dust observations",
  sim3464_geology: "Approximate rock-type classification",
};

export default function DataAvailability({ data }: { data: MarswalkData }) {
  const images = data.manifest.files.filter((file) =>
    /^panoramas\/.*\.jpg$/.test(file.path),
  ).length;
  const external = Object.entries(data.hazards.external_layers_status || {});
  return (
    <details className="source-card">
      <summary>Available data & offline use</summary>
      <h3>Included data</h3>
      <p>
        Rover stops, routes, terrain assessments, limits and supplied obstacles.
        The {images} included photos are checksum-checked when opened.
      </p>
      <p>
        {data.mode === "static"
          ? "Data loads from the configured data host."
          : "Data loads from the configured API server."}{" "}
        For offline use, download the build and serve it locally. There is no
        automatic offline browser cache.
      </p>
      <h3>Needs a connection</h3>
      <p>
        NASA maps, 3D satellite textures and additional rover photos need
        internet access. Coarse terrain remains visible without map tiles. New
        plans, route assessments and camera searches need the engine server;
        camera searches use its cache unless its operator enables NASA
        downloads.
      </p>
      <h3>Missing data & approximations</h3>
      {external.length ? (
        external.map(([name, status]) => (
          <div key={name}>
            <b>{layerNames[name] || "Additional data layer"}</b>:{" "}
            {String(status.tag ?? status.status ?? "Not reported").replaceAll(
              "_",
              " ",
            )}
            <details>
              <summary>Technical data status</summary>
              <p>{name}</p>
              {status.note && <p>{status.note}</p>}
              {status.indeterminacy_i != null
                ? ` · Scale/data uncertainty: ${status.indeterminacy_i}`
                : ""}
            </details>
          </div>
        ))
      ) : (
        <p>No external-layer availability report was supplied.</p>
      )}
      <p>
        Rock types are estimated from height and location, rather than read from
        the boundaries on the published geology map (USGS SIM 3464). Missing
        layers and terrain outside the grid remain unassessed.
      </p>
    </details>
  );
}
