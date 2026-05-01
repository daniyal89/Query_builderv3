import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { brotliCompressSync, constants as zlibConstants, gzipSync } from "node:zlib";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const distDir = path.resolve(frontendDir, "..", "frontend_dist");
const assetsDir = path.join(distDir, "assets");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
const reportPath = path.join(distDir, "build-report.json");

if (!existsSync(manifestPath)) {
  console.error(`Build manifest not found at ${manifestPath}. Run the Vite build first.`);
  process.exit(1);
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }
  return `${(kilobytes / 1024).toFixed(2)} MB`;
}

function measureAsset(relativeFile) {
  const assetPath = path.join(distDir, relativeFile);
  const content = readFileSync(assetPath);

  return {
    file: relativeFile.replace(/\\/g, "/"),
    rawBytes: content.length,
    gzipBytes: gzipSync(content).length,
    brotliBytes: brotliCompressSync(content, {
      params: {
        [zlibConstants.BROTLI_PARAM_QUALITY]: 11,
      },
    }).length,
  };
}

function sumBytes(assets, key) {
  return assets.reduce((total, asset) => total + asset[key], 0);
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
const assetReports = readdirSync(assetsDir)
  .filter((fileName) => /\.(?:css|js)$/.test(fileName))
  .map((fileName) => measureAsset(path.posix.join("assets", fileName)))
  .sort((left, right) => right.rawBytes - left.rawBytes);

const entryReports = Object.entries(manifest)
  .filter(([, asset]) => asset.isEntry)
  .map(([source, asset]) => {
    const cssAssets = (asset.css ?? []).map((cssFile) => measureAsset(cssFile));
    const entryAsset = measureAsset(asset.file);

    return {
      source,
      file: entryAsset.file,
      css: cssAssets.map((item) => item.file),
      importedChunks: (asset.imports ?? [])
        .map((importKey) => manifest[importKey]?.file)
        .filter(Boolean),
      dynamicChunks: (asset.dynamicImports ?? [])
        .map((importKey) => manifest[importKey]?.file)
        .filter(Boolean),
      rawBytes: entryAsset.rawBytes + sumBytes(cssAssets, "rawBytes"),
      gzipBytes: entryAsset.gzipBytes + sumBytes(cssAssets, "gzipBytes"),
      brotliBytes: entryAsset.brotliBytes + sumBytes(cssAssets, "brotliBytes"),
    };
  })
  .sort((left, right) => right.rawBytes - left.rawBytes);

const report = {
  generatedAt: new Date().toISOString(),
  summary: {
    assetCount: assetReports.length,
    totalRawBytes: sumBytes(assetReports, "rawBytes"),
    totalGzipBytes: sumBytes(assetReports, "gzipBytes"),
    totalBrotliBytes: sumBytes(assetReports, "brotliBytes"),
  },
  entries: entryReports,
  assets: assetReports,
};

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");

console.log(`Frontend build report written to ${reportPath}`);
console.log("Largest frontend assets:");
for (const asset of assetReports.slice(0, 8)) {
  console.log(
    `- ${asset.file}: raw ${formatBytes(asset.rawBytes)}, gzip ${formatBytes(asset.gzipBytes)}, brotli ${formatBytes(asset.brotliBytes)}`,
  );
}
