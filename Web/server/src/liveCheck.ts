/**
 * One-off live check against a real Framebase Worker. Run it yourself so the pairing secret stays in your
 * environment:  cd Web && npm run live:check
 *
 * It enrolls this machine as a library.read-only device (writes ONE row to that Worker's `devices` table),
 * loads the catalog, and fetches one thumbnail. It prints counts and folder names only, never secrets.
 */
import { CatalogIndex } from "./cloud/catalogIndex";
import { CloudClient } from "./cloud/client";
import { loadEnv } from "./env";

const env = loadEnv();
if (!env.FRAMEBASE_CLOUD_API_URL || !env.FRAMEBASE_CLOUD_PAIRING_SECRET) {
  console.error(
    "Set FRAMEBASE_CLOUD_API_URL and FRAMEBASE_CLOUD_PAIRING_SECRET (in Web/.env.local or the environment).",
  );
  process.exit(1);
}

const host = new URL(env.FRAMEBASE_CLOUD_API_URL).host;
console.log(`Worker: ${host}`);

const client = new CloudClient({
  baseUrl: env.FRAMEBASE_CLOUD_API_URL,
  pairingSecret: env.FRAMEBASE_CLOUD_PAIRING_SECRET,
  deviceId: env.FRAMEBASE_WEB_DEVICE_ID,
});

try {
  const started = Date.now();
  const { entities, watermarkRevision } = await client.fetchCatalog();
  const index = new CatalogIndex(entities, watermarkRevision, new Date().toISOString());
  const summary = index.summary();
  console.log(
    `Enrolled as "${env.FRAMEBASE_WEB_DEVICE_ID}" (library.read) and loaded the catalog in ${Date.now() - started} ms`,
  );
  console.log(
    `Assets ${summary.assetCount} · folders ${summary.folderCount} · albums ${summary.albumCount} · tags ${summary.tagCount} · revision ${summary.watermarkRevision}` +
      (index.skipped ? ` · ${index.skipped} entities skipped as malformed` : ""),
  );

  const roots = index
    .structure()
    .folders.filter((f) => f.parentId === null)
    .slice(0, 12);
  for (const f of roots) console.log(`  ${f.name.padEnd(28)} ${f.assetCount}`);

  const first = index.query({ limit: 1 }).assets[0];
  if (!first) {
    console.log("No assets in this catalog, so there is nothing to thumbnail.");
  } else {
    const res = await client.fetchVariant(first.id, "grid-256");
    const bytes = res.ok ? (await res.arrayBuffer()).byteLength : 0;
    console.log(
      `Thumbnail for "${first.displayName}": HTTP ${res.status}${res.ok ? `, ${res.headers.get("content-type")}, ${bytes} bytes` : ""}`,
    );
  }
} catch (error) {
  console.error(`Live check failed: ${error instanceof Error ? error.message : "unknown error"}`);
  process.exit(1);
}
