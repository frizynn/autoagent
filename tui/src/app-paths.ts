import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, mkdirSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** ~/.autoagent-agent/ — config, sessions, extensions */
export const appRoot = join(
  process.env.HOME || process.env.USERPROFILE || '/tmp',
  '.autoagent-agent',
);

/** ~/.autoagent-agent/agent/ — extensions, skills, etc. */
export const agentDir = join(appRoot, 'agent');

/** ~/.autoagent-agent/sessions/ — session persistence */
export const sessionsDir = join(appRoot, 'sessions');

/** ~/.autoagent-agent/auth.json — provider credentials */
export const authFilePath = join(appRoot, 'auth.json');

/** Ensure directories exist */
export function ensureDirs(): void {
  for (const dir of [appRoot, agentDir, sessionsDir]) {
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
  }
}
