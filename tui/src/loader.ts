#!/usr/bin/env node
/**
 * AutoAgent TUI Loader
 *
 * Sets PI_PACKAGE_DIR and env vars before importing cli.ts.
 * Same two-file loader pattern as GSD (D074).
 */

import { fileURLToPath } from 'node:url';
import { dirname, resolve, join, delimiter } from 'node:path';
import { existsSync, readFileSync, readdirSync, mkdirSync, symlinkSync } from 'node:fs';
import { agentDir, appRoot, ensureDirs } from './app-paths.js';

// pkg/ contains piConfig with name: "autoagent"
const pkgDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'pkg');

// MUST be set before any pi SDK import
process.env.PI_PACKAGE_DIR = pkgDir;
process.env.PI_SKIP_VERSION_CHECK = '1';
process.title = 'autoagent';

// Brief first-launch notice (onboarding wizard handles the real banner)
if (!existsSync(appRoot)) {
  const dim = '\x1b[2m';
  const reset = '\x1b[0m';
  process.stderr.write(`${dim}Setting up AutoAgent...${reset}\n`);
}

ensureDirs();

// Point pi's agent dir to our location
process.env.GSD_CODING_AGENT_DIR = agentDir;

// Make gsd-pi's node_modules available (for extensions like browser-tools)
// gsd-pi is our dependency — find it
const autoagentRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const gsdPiPath = join(autoagentRoot, 'node_modules', 'gsd-pi');
const gsdNodeModules = join(gsdPiPath, 'node_modules');

process.env.NODE_PATH = [
  join(autoagentRoot, 'node_modules'),
  gsdNodeModules,
  process.env.NODE_PATH,
].filter(Boolean).join(delimiter);

// Re-evaluate module paths
const { Module } = await import('module');
(Module as any)._initPaths?.();

// Version
process.env.AUTOAGENT_VERSION = (() => {
  try {
    return JSON.parse(readFileSync(join(autoagentRoot, 'package.json'), 'utf-8')).version || '0.1.0';
  } catch {
    return '0.1.0';
  }
})();

// Ensure workspace packages are linked from gsd-pi
const gsdScopeDir = join(autoagentRoot, 'node_modules', '@gsd');
const packagesDir = join(gsdPiPath, 'packages');
const wsPackages = ['native', 'pi-agent-core', 'pi-ai', 'pi-coding-agent', 'pi-tui'];

try {
  if (!existsSync(gsdScopeDir)) mkdirSync(gsdScopeDir, { recursive: true });
  for (const pkg of wsPackages) {
    const target = join(gsdScopeDir, pkg);
    const source = join(packagesDir, pkg);
    if (existsSync(source) && !existsSync(target)) {
      try {
        symlinkSync(source, target, 'junction');
      } catch { /* non-fatal */ }
    }
  }
} catch { /* non-fatal */ }

// Discover bundled extension paths (our autoagent extension)
const resourcesDir = join(autoagentRoot, existsSync(join(autoagentRoot, 'dist', 'resources'))
  ? join('dist', 'resources')
  : join('src', 'resources'));
const bundledExtDir = join(resourcesDir, 'extensions');
const agentExtDir = join(agentDir, 'extensions');
const discoveredPaths: string[] = [];

if (existsSync(bundledExtDir)) {
  for (const entry of readdirSync(bundledExtDir, { withFileTypes: true })) {
    if (entry.isFile() && (entry.name.endsWith('.ts') || entry.name.endsWith('.js'))) {
      discoveredPaths.push(join(agentExtDir, entry.name));
    } else if (entry.isDirectory()) {
      const idx = existsSync(join(bundledExtDir, entry.name, 'index.ts'))
        ? 'index.ts'
        : existsSync(join(bundledExtDir, entry.name, 'index.js'))
          ? 'index.js'
          : null;
      if (idx) {
        discoveredPaths.push(join(agentExtDir, entry.name, idx));
      }
    }
  }
}
process.env.GSD_BUNDLED_EXTENSION_PATHS = discoveredPaths.join('\n');

// Proxy support
import { EnvHttpProxyAgent, setGlobalDispatcher } from 'undici';
setGlobalDispatcher(new EnvHttpProxyAgent());

// Dynamic import — cli.ts will do the SDK imports
await import('./cli.js');
