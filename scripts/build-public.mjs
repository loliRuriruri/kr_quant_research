#!/usr/bin/env node
/**
 * Allowlisted Cloudflare Pages build.
 * Copies only public frontend + generated snapshot JSON.
 * Never copies .env, secrets, logs, raw data, or server code.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync, copyFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist-public");
const publicDir = join(root, "public");
const py = join(root, ".venv", "Scripts", "python.exe");

const ALLOW = [
  "index.html",
  "styles.css",
  "app.js",
  "_headers",
  "_redirects",
  "robots.txt",
];

const SECRET_PATTERNS = [
  /sk-[A-Za-z0-9_-]{10,}/,
  /xai-[A-Za-z0-9_-]{10,}/,
  /Bearer\s+[A-Za-z0-9._\-]+/i,
  /OPENDART_API_KEY\s*=/,
  /KIS_APP_SECRET\s*=/,
  /BEGIN (RSA |OPENSSH )?PRIVATE KEY/,
];

const FORBIDDEN_NAMES = [
  ".env",
  ".env.local",
  "cloudflared.exe",
  "app.py",
  "Start-KR-Quant.bat",
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
  for (const name of ALLOW) {
    const src = join(publicDir, name);
    if (!existsSync(src)) throw new Error(`missing public file: ${name}`);
    copyFileSync(src, join(dist, name));
  }
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
}

function scanSecrets() {
  const files = walk(dist);
  const hits = [];
  for (const file of files) {
    const rel = relative(dist, file).replaceAll("\\", "/");
    const base = rel.split("/").pop();
    if (FORBIDDEN_NAMES.includes(base) || rel.includes(".env")) {
      hits.push(`forbidden file ${rel}`);
      continue;
    }
    const buf = readFileSync(file);
    if (buf.includes(0)) continue;
    const text = buf.toString("utf-8");
    if (/API 설정/.test(text) && /key-opendart|settings\/raw/.test(text)) {
      hits.push(`settings UI leaked in ${rel}`);
    }
    if (rel === "app.js" && /\/api\/settings\/raw|data-view="settings"|btn-toggle-pw/.test(text)) {
      hits.push(`admin settings UI leaked in ${rel}`);
    }
    for (const re of SECRET_PATTERNS) {
      if (re.test(text)) hits.push(`secret pattern ${re} in ${rel}`);
    }
  }
  if (!files.some((f) => relative(dist, f).replaceAll("\\", "/").endsWith("index.html"))) {
    hits.push("index.html missing");
  }
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
  const info = {
    project: "korea-quant-research",
    generated_at: new Date().toISOString(),
    files,
    bundle_sha256: hash.digest("hex"),
    settings_ui: false,
    ai_run_ui: false,
  };
  writeFileSync(join(dist, "build.json"), JSON.stringify(info, null, 2));
}

if (existsSync(dist)) rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyAllowlisted();
exportSnapshot();
writeBuildInfo();
scanSecrets();
console.log(`dist-public ready (${walk(dist).length} files)`);
