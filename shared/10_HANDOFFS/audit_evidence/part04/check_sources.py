"""Bounded HEAD diagnostics for manifest URLs; no raw payload downloads."""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
manifest = json.loads((ROOT / "public_packs/jezero/v1/manifest.json").read_text(encoding="utf-8"))


def check(source):
    request = urllib.request.Request(
        source["url"], method="HEAD", headers={"User-Agent": "Marswalk-Source-Audit/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {
                "id": source["id"],
                "url": source["url"],
                "status": response.status,
                "final_url": response.url,
            }
    except urllib.error.HTTPError as error:
        return {"id": source["id"], "url": source["url"], "status": error.code}
    except Exception as error:
        return {
            "id": source["id"],
            "url": source["url"],
            "error": type(error).__name__ + ": " + str(error),
        }


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(check, manifest["sources"]))
    output = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "HEAD only; HTTP errors do not prove a source invalid; payload/science not validated"
        ),
        "results": results,
    }
    text = json.dumps(output, indent=2)
    (Path(__file__).parent / "source-head-results.json").write_text(text, encoding="utf-8")
    print(text)
