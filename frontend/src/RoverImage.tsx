import { useEffect, useState } from "react";
import { ExternalLink, MapPinned } from "lucide-react";
import { safeUrl } from "./domain";
import { getConfig } from "./data/config";
import { bundledImagePath, loadBundledImage } from "./data/images";
import type { MarswalkData } from "./data/types";

export default function RoverImage({
  data,
  url,
}: {
  data: MarswalkData;
  url?: string | null;
}) {
  const original = safeUrl(url);
  const [src, setSrc] = useState<string>();
  const [status, setStatus] = useState<
    "loading" | "bundled" | "remote" | "failed"
  >("loading");
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setSrc(undefined);
    setStatus("loading");
    const path = bundledImagePath(data, original);
    if (path) {
      loadBundledImage(getConfig(), data.manifest, path, controller.signal)
        .then((blob) => {
          if (controller.signal.aborted) return;
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
          setStatus("bundled");
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setSrc(original);
            setStatus(original ? "remote" : "failed");
          }
        });
    } else {
      setSrc(original);
      setStatus(original ? "remote" : "failed");
    }
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [data, original]);
  return (
    <div className="panorama">
      {src && status !== "failed" ? (
        <img
          src={src}
          alt="Perseverance Navcam image from the selected rover stop"
          loading="lazy"
          onError={() => {
            if (status === "bundled" && original) {
              setSrc(original);
              setStatus("remote");
            } else setStatus("failed");
          }}
        />
      ) : (
        <div className="image-fallback">
          <MapPinned size={24} />
          <span>
            {status === "loading"
              ? "Loading rover image…"
              : original
                ? "Rover image could not be loaded"
                : "No rover image available"}
          </span>
        </div>
      )}
      {src && status !== "failed" && (
        <p className="footnote">
          Navcam frame · MEASURED · NASA/JPL-Caltech
          {status === "bundled"
            ? " · Verified pack copy"
            : " · NASA network image"}
          . This is a camera frame, not a 360° panorama.
        </p>
      )}
      {original && (
        <a href={original} target="_blank" rel="noreferrer">
          Open NASA image <ExternalLink size={12} />
        </a>
      )}
    </div>
  );
}
