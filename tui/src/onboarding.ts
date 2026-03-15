/**
 * AutoAgent onboarding — minimal first-run setup.
 *
 * Guides the user through LLM provider selection on first launch.
 * Clean, minimal, branded as AutoAgent — not GSD.
 */

import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { AuthStorage } from '@gsd/pi-coding-agent';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Known LLM provider IDs
const LLM_PROVIDERS = [
  'anthropic', 'openai', 'github-copilot', 'openai-codex',
  'google-gemini-cli', 'google-antigravity', 'google',
  'groq', 'xai', 'openrouter', 'mistral', 'ollama-cloud', 'custom-openai',
];

const API_KEY_PREFIXES: Record<string, string[]> = {
  anthropic: ['sk-ant-'],
  openai: ['sk-'],
};

async function loadClack() {
  return await import('@clack/prompts');
}

async function loadPico() {
  try {
    const mod = await import('picocolors');
    return mod.default ?? mod;
  } catch {
    const id = (s: string) => s;
    return { cyan: id, green: id, yellow: id, dim: id, bold: id, red: id, reset: id, magenta: id, white: id };
  }
}

/** Open URL in browser (best-effort) */
function openBrowser(url: string): void {
  import('node:child_process').then(({ exec }) => {
    const cmd = process.platform === 'darwin' ? 'open' :
      process.platform === 'win32' ? 'start' : 'xdg-open';
    exec(`${cmd} "${url}"`, () => {});
  });
}

export function shouldRunOnboarding(authStorage: AuthStorage): boolean {
  if (!process.stdin.isTTY) return false;
  return !LLM_PROVIDERS.some(id => authStorage.hasAuth(id));
}

export async function runOnboarding(authStorage: AuthStorage): Promise<void> {
  let p: any;
  let c: any;

  try {
    [p, c] = await Promise.all([loadClack(), loadPico()]);
  } catch (err: any) {
    process.stderr.write(`[autoagent] Setup unavailable: ${err.message}\n`);
    return;
  }

  // ── Banner ──────────────────────────────────────────────────────────
  const version = process.env.AUTOAGENT_VERSION || '0.1.0';
  process.stderr.write('\n');
  process.stderr.write(`  ${c.cyan(c.bold('⚡ AutoAgent'))} ${c.dim(`v${version}`)}\n`);
  process.stderr.write(`  ${c.dim('Autonomous optimization for agentic architectures')}\n\n`);

  p.intro(c.white('First-time setup'));

  // ── LLM Provider ────────────────────────────────────────────────────
  const method = await p.select({
    message: 'Choose how to connect your LLM provider',
    options: [
      { value: 'api-key', label: 'Paste an API key', hint: 'Anthropic, OpenAI, or others' },
      { value: 'browser', label: 'Sign in with browser', hint: 'OAuth — Claude, Copilot, Gemini' },
      { value: 'skip', label: 'Skip', hint: 'configure later with /login' },
    ],
  });

  if (p.isCancel(method) || method === 'skip') {
    p.outro(c.dim('You can configure your provider anytime with /login'));
    return;
  }

  let llmConfigured = false;

  if (method === 'api-key') {
    const provider = await p.select({
      message: 'Provider',
      options: [
        { value: 'anthropic', label: 'Anthropic (Claude)', hint: 'recommended' },
        { value: 'openai', label: 'OpenAI' },
        { value: 'google', label: 'Google (Gemini)' },
        { value: 'openrouter', label: 'OpenRouter' },
        { value: 'groq', label: 'Groq' },
        { value: 'xai', label: 'xAI (Grok)' },
        { value: 'mistral', label: 'Mistral' },
      ],
    });

    if (!p.isCancel(provider)) {
      const key = await p.password({
        message: `API key`,
        mask: '•',
      });

      if (!p.isCancel(key) && key?.trim()) {
        const trimmed = key.trim();
        const prefixes = API_KEY_PREFIXES[provider as string];
        if (prefixes && !prefixes.some((pfx: string) => trimmed.startsWith(pfx))) {
          p.log.warn(`Unexpected prefix — saving anyway.`);
        }
        authStorage.set(provider as string, { type: 'api_key', key: trimmed } as any);
        p.log.success(`${c.green('✓')} Saved`);
        llmConfigured = true;
      }
    }
  } else if (method === 'browser') {
    const provider = await p.select({
      message: 'Provider',
      options: [
        { value: 'anthropic', label: 'Anthropic (Claude)' },
        { value: 'github-copilot', label: 'GitHub Copilot' },
        { value: 'openai-codex', label: 'ChatGPT Plus/Pro' },
        { value: 'google-gemini-cli', label: 'Google Gemini CLI' },
      ],
    });

    if (!p.isCancel(provider)) {
      const oauthProviders = (authStorage as any).getOAuthProviders?.() ?? [];
      const providerInfo = oauthProviders.find((op: any) => op.id === provider);
      const usesCallback = providerInfo?.usesCallbackServer ?? false;

      const s = p.spinner();
      s.start('Authenticating...');

      try {
        await authStorage.login(provider as string, {
          onAuth: (info: any) => {
            s.stop('Opening browser');
            openBrowser(info.url);
            p.log.info(`${c.dim('URL:')} ${c.cyan(info.url)}`);
            if (info.instructions) p.log.info(c.yellow(info.instructions));
          },
          onPrompt: async (prompt: any) => {
            const result = await p.text({ message: prompt.message, placeholder: prompt.placeholder });
            return p.isCancel(result) ? '' : result;
          },
          onProgress: (msg: string) => p.log.step(c.dim(msg)),
          onManualCodeInput: usesCallback
            ? async () => {
                const result = await p.text({ message: 'Paste the redirect URL:', placeholder: 'http://localhost:...' });
                return p.isCancel(result) ? '' : result;
              }
            : undefined,
        });
        p.log.success(`${c.green('✓')} Authenticated`);
        llmConfigured = true;
      } catch (err: any) {
        s.stop('Authentication failed');
        const msg = err instanceof Error ? err.message : String(err);
        p.log.warn(`Auth error: ${msg}`);
        p.log.info(c.dim('You can try again with /login inside the TUI'));
      }
    }
  }

  // ── Done ────────────────────────────────────────────────────────────
  if (llmConfigured) {
    p.outro(c.dim('Ready — launching AutoAgent'));
  } else {
    p.outro(c.dim('No provider configured — use /login inside the TUI'));
  }
}

/**
 * Load stored env keys (tool API keys) from auth.json into process.env.
 */
export function loadStoredEnvKeys(authStorage: AuthStorage): void {
  const toolKeys = [
    { provider: 'context7', envVar: 'CONTEXT7_API_KEY' },
    { provider: 'jina', envVar: 'JINA_API_KEY' },
    { provider: 'groq', envVar: 'GROQ_API_KEY' },
    { provider: 'brave', envVar: 'BRAVE_API_KEY' },
    { provider: 'tavily', envVar: 'TAVILY_API_KEY' },
  ];

  for (const { provider, envVar } of toolKeys) {
    if (process.env[envVar]) continue; // Don't override existing env vars
    try {
      const auth = authStorage.get(provider);
      if (auth && (auth as any).key) {
        process.env[envVar] = (auth as any).key;
      }
    } catch {
      // Not stored — skip
    }
  }
}
