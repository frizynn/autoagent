/**
 * AutoAgent CLI — interactive TUI powered by Pi SDK.
 *
 * Creates an agent session with the autoagent extension loaded,
 * then runs InteractiveMode for the full chat TUI experience.
 */

import {
  AuthStorage,
  DefaultResourceLoader,
  ModelRegistry,
  SettingsManager,
  SessionManager,
  createAgentSession,
  InteractiveMode,
  runPrintMode,
} from '@gsd/pi-coding-agent';
import { existsSync, readFileSync, readdirSync, mkdirSync, copyFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { agentDir, sessionsDir, authFilePath, appRoot } from './app-paths.js';

// ---------------------------------------------------------------------------
// Resource syncing — copy bundled extensions to agentDir
// ---------------------------------------------------------------------------

function syncResources(): void {
  const autoagentRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const srcResources = join(autoagentRoot, 'src', 'resources');
  const distResources = join(autoagentRoot, 'dist', 'resources');
  const resourcesDir = existsSync(distResources) ? distResources : srcResources;

  if (!existsSync(resourcesDir)) return;

  const extSrc = join(resourcesDir, 'extensions');
  const extDst = join(agentDir, 'extensions');

  if (!existsSync(extSrc)) return;
  mkdirSync(extDst, { recursive: true });

  // Sync extension directories
  for (const entry of readdirSync(extSrc, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      const srcDir = join(extSrc, entry.name);
      const dstDir = join(extDst, entry.name);
      mkdirSync(dstDir, { recursive: true });

      for (const file of readdirSync(srcDir)) {
        copyFileSync(join(srcDir, file), join(dstDir, file));
      }
    } else if (entry.isFile()) {
      copyFileSync(join(extSrc, entry.name), join(extDst, entry.name));
    }
  }
}

// ---------------------------------------------------------------------------
// CLI arg parsing
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]): {
  print?: boolean;
  continue?: boolean;
  model?: string;
  messages: string[];
} {
  const flags: { print?: boolean; continue?: boolean; model?: string; messages: string[] } = {
    messages: [],
  };
  const args = argv.slice(2);

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--print' || arg === '-p') {
      flags.print = true;
    } else if (arg === '--continue' || arg === '-c') {
      flags.continue = true;
    } else if (arg === '--model' && i + 1 < args.length) {
      flags.model = args[++i];
    } else if (arg === '--version' || arg === '-v') {
      process.stdout.write((process.env.AUTOAGENT_VERSION || '0.1.0') + '\n');
      process.exit(0);
    } else if (arg === '--help' || arg === '-h') {
      process.stdout.write(`AutoAgent v${process.env.AUTOAGENT_VERSION || '0.1.0'}\n\n`);
      process.stdout.write('Usage: autoagent [options] [message...]\n\n');
      process.stdout.write('Options:\n');
      process.stdout.write('  --print, -p      Single-shot mode\n');
      process.stdout.write('  --continue, -c   Resume recent session\n');
      process.stdout.write('  --model <id>     Override model\n');
      process.stdout.write('  --version, -v    Print version\n');
      process.stdout.write('  --help, -h       Print this help\n');
      process.stdout.write('\nCommands (inside TUI):\n');
      process.stdout.write('  /autoagent run   Start optimization loop\n');
      process.stdout.write('  /autoagent stop  Stop running loop\n');
      process.stdout.write('  /autoagent new   Configure project via interview\n');
      process.stdout.write('  /autoagent report  View optimization report\n');
      process.stdout.write('  /autoagent status  Show project status\n');
      process.exit(0);
    } else if (!arg.startsWith('-')) {
      flags.messages.push(arg);
    }
  }

  return flags;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const cliFlags = parseArgs(process.argv);

const authStorage = AuthStorage.create(authFilePath);
const modelRegistry = new ModelRegistry(authStorage);
const settingsManager = SettingsManager.create(agentDir);

// Auto-select a model if none configured
const configuredModel = settingsManager.getDefaultModel();
if (!configuredModel) {
  const available = modelRegistry.getAvailable();
  const preferred =
    available.find((m: any) => m.provider === 'anthropic' && m.id.includes('sonnet')) ||
    available.find((m: any) => m.provider === 'anthropic') ||
    available.find((m: any) => m.provider === 'openai') ||
    available[0];

  if (preferred) {
    settingsManager.setDefaultModelAndProvider(preferred.provider, preferred.id);
  }
}

// Quiet startup — our extension handles branding
if (!settingsManager.getQuietStartup()) {
  settingsManager.setQuietStartup(true);
}

// Sync bundled extensions
syncResources();

// Session management
const cwd = process.cwd();
const safePath = `--${cwd.replace(/^[/\\]/, '').replace(/[/\\:]/g, '-')}--`;
const projectSessionsDir = join(sessionsDir, safePath);

const sessionManager = cliFlags.continue
  ? SessionManager.continueRecent(cwd, projectSessionsDir)
  : SessionManager.create(cwd, projectSessionsDir);

const resourceLoader = new DefaultResourceLoader({ agentDir });
await resourceLoader.reload();

const { session, extensionsResult } = await createAgentSession({
  authStorage,
  modelRegistry,
  settingsManager,
  sessionManager,
  resourceLoader,
});

if (extensionsResult.errors.length > 0) {
  for (const err of extensionsResult.errors) {
    process.stderr.write(`[autoagent] Extension error: ${err.error}\n`);
  }
}

// Apply --model override
if (cliFlags.model) {
  const available = modelRegistry.getAvailable();
  const match =
    available.find((m: any) => m.id === cliFlags.model) ||
    available.find((m: any) => `${m.provider}/${m.id}` === cliFlags.model);
  if (match) {
    session.setModel(match);
  }
}

// Print mode
if (cliFlags.print) {
  await runPrintMode(session, {
    mode: 'text',
    messages: cliFlags.messages,
  });
  process.exit(0);
}

// Interactive mode
if (!process.stdin.isTTY) {
  process.stderr.write('[autoagent] Error: Interactive mode requires a terminal.\n');
  process.stderr.write('[autoagent] Use: autoagent --print "your message"\n');
  process.exit(1);
}

const interactiveMode = new InteractiveMode(session);
await interactiveMode.run();
