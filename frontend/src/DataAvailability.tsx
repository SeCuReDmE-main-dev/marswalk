import type { MarswalkData } from "./data/types";

export default function DataAvailability({ data }: { data: MarswalkData }) {
  const images = data.manifest.files.filter((file) =>
    /^panoramas\/.*\.jpg$/.test(file.path),
  ).length;
  const external = Object.entries(data.hazards.external_layers_status || {});
  return (
    <details className="source-card">
      <summary>Local data & network limits</summary>
      <h3>Included in the pack</h3>
      <p>
        Rover observations, supplied routes, terrain assessments, constraints
        and obstacles when supplied. {images} rover images are bundled; each
        image is checked against the manifest when opened.
      </p>
      <p>
        {data.mode === "static"
          ? "This session loads its pack from the configured static host."
          : "This session loads its pack from the configured API server."}{" "}
        Bundled data still needs that host to be reachable. Offline use requires
        serving the downloaded build locally; this app does not install an
        offline browser cache.
      </p>
      <h3>Needs a connection</h3>
      <p>
        NASA map tiles, the 3D satellite texture and unbundled rover photos need
        NASA access. Coarse elevation relief remains available without tiles.
        New route planning, path assessment and camera-cache lookup need the
        configured engine server. The camera browser requests cached images
        only; live NASA fetching requires operator permission on the server.
      </p>
      <h3>Missing data & approximations</h3>
      {external.length ? (
        external.map(([name, status]) => (
          <p key={name}>
            <b>{name}</b>:{" "}
            {String(status.tag ?? status.status ?? "Not reported").replaceAll(
              "_",
              " ",
            )}
            {status.note ? ` · ${status.note}` : ""}
            {status.indeterminacy_i != null
              ? ` · Scale/data uncertainty: ${status.indeterminacy_i}`
              : ""}
          </p>
        ))
      ) : (
        <p>No external-layer availability report was supplied.</p>
      )}
      <p>
        Geological units use an elevation/position approximation, not the
        published SIM 3464 polygons. Missing layers are not invented. Outside
        the assessed window, terrain remains unassessed.
      </p>
    </details>
  );
}
