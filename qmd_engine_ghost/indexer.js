#!/usr/bin/env node
/**
 * QMD Wrapper Plugin - Indexer Script
 *
 * Uses the QMD CLI to add collections and rebuild the index.
 * Called by execute.py during plugin setup.
 *
 * Usage: node indexer.js <indexDir> <sourcePath1> [sourcePath2 ...]
 *
 * NOTE: indexDir is accepted for backwards compatibility but QMD uses its
 * own default database path (~/.cache/qmd/index.sqlite).
 */

import { execFileSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { existsSync } from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const QMD_CLI = join(__dirname, "node_modules", "@tobilu", "qmd", "dist", "cli", "qmd.js");

if (!existsSync(QMD_CLI)) {
  console.error("[QMD] ERROR: QMD CLI not found at", QMD_CLI);
  process.exit(1);
}

// Parse args: node indexer.js <indexDir> <path1> [path2 ...]
const [, , _indexDir, ...sourcePaths] = process.argv;

if (!sourcePaths.length) {
  console.error("[QMD] ERROR: No source paths provided");
  process.exit(1);
}

try {
  for (const srcPath of sourcePaths) {
    console.log(`[QMD] Adding collection: ${srcPath}`);
    execFileSync("node", [QMD_CLI, "collection", "add", srcPath], {
      stdio: "inherit",
      cwd: __dirname,
    });
  }

  console.log("[QMD] Updating index...");
  execFileSync("node", [QMD_CLI, "update"], { stdio: "inherit", cwd: __dirname });

  console.log(JSON.stringify({ success: true, indexedPaths: sourcePaths }));
} catch (err) {
  console.error(JSON.stringify({ error: err.message }));
  process.exit(1);
}
