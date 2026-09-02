#!/usr/bin/env node
/**
 * Allowlisted Cloudflare Pages build.
 * Copies the local dashboard frontend + generated read-only snapshot JSON.
 * Never copies .env, secrets, logs, raw data, or server code.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync, copyFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist-public");
const publicDir = join(root, "public");
const staticDir = join(root, "src", "kr_quant", "web", "static");
const py = join(root, ".venv", "Scripts", "python.exe");
const reuseExistingData = process.argv.includes("--reuse-data");
const preservedData = join(root, ".runtime", "public-data-reuse");

const FRONTEND_FILES = ["index.html", "styles.css", "app.js"];
const PUBLIC_META_FILES = ["_headers", "_redirects", "robots.txt"];

const SECRET_PATTERNS = [
  /sk-[A-Za-z0-9_-]{10,}/,
  /xai-[A-Za-z0-9_-]{10,}/,
  /Bearer\s+[A-Za-z0-9._\-]+/i,
  /(?:OPENDART|DART|KRX|ECOS|FRED)_API_KEY\s*=\s*[^\s]/i,
  /KIS_APP_SECRET\s*=\s*[^\s]/i,
  /ghp_[A-Za-z0-9]{30,}/,
  /github_pat_[A-Za-z0-9_]{40,}/,
  /BEGIN (RSA |OPENSSH )?PRIVATE KEY/,
];

const FORBIDDEN_NAMES = [
  ".env",
  ".env.local",
  "cloudflared.exe",
  "app.py",
  "Start-KR-Quant.bat",
  "Stop-KR-Quant.bat",
];

const FORBIDDEN_EXTENSIONS = [
  ".env",
  ".log",
  ".parquet",
  ".tmp",
  ".bak",
  ".ps1",
  ".bat",
  ".py",
  ".cmd",
  ".sh",
  ".exe",
];

const LOCAL_PATH_PATTERNS = [
  /[A-Za-z]:\\(?:Users|home)\b/i,
  /[A-Za-z]:\/(?:Users|home)\b/i,
  /(?:^|["'\s])\/(?:Users|home)\/[A-Za-z0-9_.-]+/i,
];

function walk(dir, acc = []) {
  if (!existsSync(dir)) return acc;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, acc);
    else acc.push(p);
  }
  return acc;
}

function copyAllowlisted() {
  mkdirSync(dist, { recursive: true });
  for (const name of FRONTEND_FILES) {
    const src = join(staticDir, name);
    if (!existsSync(src)) throw new Error(`missing local frontend file: ${name}`);
    copyFileSync(src, join(dist, name));
  }
  for (const name of PUBLIC_META_FILES) {
    const src = join(publicDir, name);
    if (!existsSync(src)) throw new Error(`missing public metadata file: ${name}`);
    copyFileSync(src, join(dist, name));
  }

  const buildId = Date.now().toString(36);
  const indexPath = join(dist, "index.html");
  const index = readFileSync(indexPath, "utf-8")
    .replace("<body>", '<body data-public-build="true">')
    .replace(/\/static\/styles\.css\?v=[^"']+/, `/styles.css?v=${buildId}`)
    .replace(/\/static\/app\.js\?v=[^"']+/, `/app.js?v=${buildId}`);
  writeFileSync(indexPath, index, "utf-8");
}

function exportSnapshot() {
  const out = join(dist, "data");
  mkdirSync(out, { recursive: true });
  const bin = existsSync(py) ? py : "python";
  const r = spawnSync(bin, [join(root, "scripts", "export_public_snapshot.py"), "--out", out], {
    cwd: root,
    encoding: "utf-8",
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (r.status !== 0) {
    throw new Error(`snapshot export failed: ${r.stderr || r.stdout || r.status}`);
  }
  process.stdout.write(r.stdout || "");

  const apiOut = join(out, "api");
  mkdirSync(apiOut, { recursive: true });
  const apiResult = spawnSync(bin, [join(root, "scripts", "export_public_ui_api.py"), "--out", apiOut], {
    cwd: root,
    encoding: "utf-8",
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (apiResult.status !== 0) {
    throw new Error(`full UI API snapshot export failed: ${apiResult.stderr || apiResult.stdout || apiResult.status}`);
  }
  process.stdout.write(apiResult.stdout || "");
}

function configuredSecrets() {
  const envPath = join(root, ".env");
  if (!existsSync(envPath)) return [];
  return readFileSync(envPath, "utf-8").split(/\r?\n/).flatMap((line) => {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!match || !/(KEY|SECRET|TOKEN|PASSWORD)/i.test(match[1])) return [];
    const value = match[2].replace(/^(["'])(.*)\1$/, "$2").trim();
    return value.length >= 8 ? [{ name: match[1], value }] : [];
  });
}

function scanSecrets() {
  const files = walk(dist);
  const hits = [];
  const localSecrets = configuredSecrets();
  for (const file of files) {
    const rel = relative(dist, file).replaceAll("\\", "/");
    const base = rel.split("/").pop() || "";
    if (FORBIDDEN_NAMES.includes(base) || rel.includes(".env")) {
      hits.push(`forbidden file ${rel}`);
      continue;
    }
    const lowerBase = base.toLowerCase();
    if (FORBIDDEN_EXTENSIONS.some((ext) => lowerBase.endsWith(ext))) {
      hits.push(`forbidden extension file ${rel}`);
      continue;
    }
    const buf = readFileSync(file);
    if (buf.includes(0)) continue;
    const text = buf.toString("utf-8");
    for (const re of SECRET_PATTERNS) {
      if (re.test(text)) hits.push(`secret pattern ${re} in ${rel}`);
    }
    for (const secret of localSecrets) {
      if (text.includes(secret.value)) hits.push(`configured ${secret.name} value in ${rel}`);
    }
    for (const pathRe of LOCAL_PATH_PATTERNS) {
      if (pathRe.test(text)) hits.push(`local absolute path pattern ${pathRe} in ${rel}`);
    }
  }
  if (!files.some((f) => relative(dist, f).replaceAll("\\", "/").endsWith("index.html"))) {
    hits.push("index.html missing");
  }
  const publicIndex = readFileSync(join(dist, "index.html"), "utf-8");
  if (!publicIndex.includes('data-public-build="true"')) hits.push("public build marker missing");
  if (/\/static\/(?:app\.js|styles\.css)/.test(publicIndex)) hits.push("local static asset path leaked into public index");
  if (hits.length) throw new Error(`public build scan failed:\n- ${hits.join("\n- ")}`);
}

function writeBuildInfo() {
  const files = walk(dist).map((f) => relative(dist, f).replaceAll("\\", "/")).sort();
  const hash = createHash("sha256");
  for (const rel of files) {
    if (rel === "build.json") continue;
    hash.update(rel);
    hash.update(readFileSync(join(dist, rel)));
  }

  let gitCommit = "unknown";
  try {
    const gitRes = spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf-8" });
    if (gitRes.status === 0 && gitRes.stdout) {
      gitCommit = gitRes.stdout.trim();
    }
  } catch (e) {}

  let dataAsOf = null;
  let sourceHashes = {};
  const metaPath = join(dist, "data", "meta.json");
  if (existsSync(metaPath)) {
    try {
      const m = JSON.parse(readFileSync(metaPath, "utf-8"));
      dataAsOf = m.as_of_date || m.as_of || null;
      sourceHashes = {
        source_bundle_hash: m.source_bundle_hash || null,
        result_hash: m.result_hash || null,
        config_hash: m.config_hash || null,
      };
    } catch (e) {}
  }
  if (!dataAsOf) {
    const manifestPath = join(dist, "data", "api", "manifest.json");
    if (existsSync(manifestPath)) {
      try {
        const man = JSON.parse(readFileSync(manifestPath, "utf-8"));
        dataAsOf = man.as_of || null;
      } catch (e) {}
    }
  }

  const info = {
    project: "korea-quant-research",
    schema_version: "1.1.0",
    git_commit: gitCommit,
    data_as_of: dataAsOf,
    source_hashes: sourceHashes,
    generated_at: new Date().toISOString(),
    web_deployed_at: new Date().toISOString(),
    reuse_existing_data: reuseExistingData,
    files,
    bundle_sha256: hash.digest("hex"),
    full_local_ui: true,
    read_only: true,
    settings_ui: false,
    ai_run_ui: false,
  };
  writeFileSync(join(dist, "build.json"), JSON.stringify(info, null, 2));
}

if (reuseExistingData) {
  const currentData = join(dist, "data");
  const manifest = join(currentData, "api", "manifest.json");
  if (!existsSync(manifest)) {
    throw new Error("code-only build requires an existing dist-public/data/api/manifest.json snapshot");
  }
  rmSync(preservedData, { recursive: true, force: true });
  mkdirSync(dirname(preservedData), { recursive: true });
  cpSync(currentData, preservedData, { recursive: true });
}
if (existsSync(dist)) rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyAllowlisted();
if (reuseExistingData) {
  cpSync(preservedData, join(dist, "data"), { recursive: true });
  rmSync(preservedData, { recursive: true, force: true });
  console.log("reused existing public data snapshot; frontend files refreshed");
} else {
  exportSnapshot();
}
writeBuildInfo();
scanSecrets();
console.log(`dist-public ready (${walk(dist).length} files)`);
