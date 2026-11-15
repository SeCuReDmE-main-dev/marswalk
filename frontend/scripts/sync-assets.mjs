import { cp, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = new URL("../../", import.meta.url);
for (const [source, target] of [
  ["public_packs/jezero/v1/", "frontend/public/data/jezero/v1/"],
]) {
  const destination = new URL(target, root);
  await mkdir(destination, { recursive: true });
  await cp(new URL(source, root), destination, { recursive: true });
  console.log("Copied read-only source assets to", fileURLToPath(destination));
}
const brand = new URL("frontend/public/brand/", root);
await mkdir(brand, { recursive: true });
for (const file of [
  "marswalk-mark.svg",
  "marswalk-logo.svg",
  "marswalk-logo-inverse.svg",
])
  await cp(new URL(`docs/brand/marswalk/${file}`, root), new URL(file, brand));
console.log("Copied selected Marswalk logo assets");
