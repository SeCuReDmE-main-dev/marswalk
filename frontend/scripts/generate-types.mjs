import { compileFromFile } from "json-schema-to-typescript";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { format } from "prettier";
const names = [
  "SiteManifest",
  "WaypointFeatureCollection",
  "EvaRoute",
  "HazardGrid",
  "EvaConstraints",
];
await mkdir(new URL("../src/data/generated/", import.meta.url), {
  recursive: true,
});
for (const name of names) {
  const schema = new URL(`../../schemas/${name}.schema.json`, import.meta.url);
  const content = await compileFromFile(fileURLToPath(schema), {
    bannerComment:
      "/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */",
  });
  await writeFile(
    new URL(`../src/data/generated/${name}.ts`, import.meta.url),
    await format(content, { parser: "typescript" }),
  );
  console.log("Generated", name);
}
