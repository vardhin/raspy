<script lang="ts">
	// Terminal app — a real interactive shell on the Pi, streamed over the
	// encrypted channel. Admin-only (backend 403s / closes the WS otherwise).
	//
	// The PTY WebSocket REQUIRES the channel: we open it with ?channel=<sid> and
	// seal/open every frame with the same session the rest of the app uses, so
	// keystrokes (and any sudo password you type) never cross the tunnel in clear.
	// Sessions are tmux-like — they survive a tab close and can be reattached.
	import { onMount, onDestroy } from 'svelte';
	import { attGet, attAction, wsUrl } from '$lib/api';
	import { channel } from '$lib/crypto/channel';
	import { Button, Icon, Stack, Text } from '$lib/components';
	import { Terminal as Xterm } from '@xterm/xterm';
	import { FitAddon } from '@xterm/addon-fit';
	import '@xterm/xterm/css/xterm.css';

	interface Shell {
		id: string;
		name: string;
		path: string;
	}
	interface SessionInfo {
		id: string;
		shell: string;
		cols: number;
		rows: number;
		attached: boolean;
		alive: boolean;
	}

	let { node }: { node: { title?: string } } = $props();

	let supported = $state(true);
	let shells = $state<Shell[]>([]);
	let sessions = $state<SessionInfo[]>([]);
	let activeShell = $state<string>('');
	let status = $state<'idle' | 'connecting' | 'open' | 'closed'>('idle');
	let error = $state<string | null>(null);

	let host = $state<HTMLDivElement>();
	let term: Xterm | null = null;
	let fit: FitAddon | null = null;
	let ws: WebSocket | null = null;
	let resizeObserver: ResizeObserver | null = null;
	// The session id once the server reports it; lets us reattach after a drop.
	let currentSid = $state<string | null>(null);

	onMount(async () => {
		try {
			const s = await attGet<{ supported: boolean; shells: Shell[] }>('terminal', 'shells');
			supported = s.supported;
			shells = s.shells;
			activeShell = shells[0]?.path ?? '';
			await refreshSessions();
		} catch (e) {
			error = (e as Error)?.message ?? 'failed to load shells';
		}
	});

	onDestroy(() => teardown());

	async function refreshSessions() {
		try {
			const r = await attGet<{ sessions: SessionInfo[] }>('terminal', 'sessions');
			sessions = r.sessions.filter((s) => s.alive);
		} catch {
			/* non-fatal */
		}
	}

	function teardown() {
		resizeObserver?.disconnect();
		resizeObserver = null;
		ws?.close();
		ws = null;
		term?.dispose();
		term = null;
		fit = null;
		status = 'idle';
	}

	async function seal(message: object): Promise<string> {
		const payload = await channel.seal(new TextEncoder().encode(JSON.stringify(message)));
		return JSON.stringify({ type: 'sealed', payload });
	}

	function send(message: object) {
		if (ws?.readyState === WebSocket.OPEN) {
			void seal(message).then((frame) => ws?.send(frame));
		}
	}

	function ensureTerm() {
		if (term || !host) return;
		term = new Xterm({
			fontFamily: 'var(--font-mono, monospace)',
			fontSize: 13,
			cursorBlink: true,
			// Pull a few colours from the active theme so it blends with the app.
			theme: readThemeColors(),
			scrollback: 5000
		});
		fit = new FitAddon();
		term.loadAddon(fit);
		term.open(host);
		fit.fit();
		// Keystrokes → server.
		term.onData((data) => send({ t: 'input', data }));
		// Re-fit + tell the PTY when the container resizes.
		resizeObserver = new ResizeObserver(() => doFit());
		resizeObserver.observe(host);
	}

	function doFit() {
		if (!fit || !term) return;
		try {
			fit.fit();
			send({ t: 'resize', cols: term.cols, rows: term.rows });
		} catch {
			/* element not measurable yet */
		}
	}

	function readThemeColors(): Record<string, string> {
		if (typeof getComputedStyle === 'undefined') return {};
		const cs = getComputedStyle(document.documentElement);
		const v = (n: string, fallback: string) => cs.getPropertyValue(n).trim() || fallback;
		return {
			background: v('--surface-2', '#1e1e1e'),
			foreground: v('--fg', '#e0e0e0'),
			cursor: v('--accent', '#9af')
		};
	}

	async function connect(attachSid: string | null) {
		if (!supported) {
			error = 'Terminal is not supported on this platform.';
			return;
		}
		error = null;
		teardown();
		ensureTerm();
		status = 'connecting';

		// The PTY WS demands the channel; establish it before connecting.
		try {
			await channel.ensure();
		} catch (e) {
			error = (e as Error)?.message ?? 'secure channel unavailable';
			status = 'closed';
			return;
		}
		const sid = channel.sessionId;
		if (!sid) {
			error = 'secure channel unavailable';
			status = 'closed';
			return;
		}
		const socket = new WebSocket(wsUrl(`/api/att/terminal/pty?channel=${encodeURIComponent(sid)}`));
		ws = socket;

		socket.addEventListener('open', () => {
			status = 'open';
			if (attachSid) {
				send({ t: 'attach', sid: attachSid });
			} else {
				send({ t: 'open', shell: activeShell, cols: term?.cols ?? 80, rows: term?.rows ?? 24 });
			}
		});
		socket.addEventListener('message', (ev) => void onFrame(String(ev.data)));
		socket.addEventListener('close', () => {
			if (ws === socket) {
				status = 'closed';
				void refreshSessions();
			}
		});
		socket.addEventListener('error', () => {
			error = 'connection error';
		});
	}

	async function onFrame(raw: string) {
		let msg: { t?: string; data?: string; sid?: string; code?: number; msg?: string };
		try {
			const frame = JSON.parse(raw);
			if (frame.type !== 'sealed') return;
			const plain = await channel.open(frame.payload);
			msg = JSON.parse(new TextDecoder().decode(plain));
		} catch {
			return;
		}
		switch (msg.t) {
			case 'ready':
				currentSid = msg.sid ?? null;
				doFit();
				term?.focus();
				void refreshSessions();
				break;
			case 'output':
				if (msg.data) term?.write(msg.data);
				break;
			case 'exit':
				term?.write(`\r\n\x1b[90m[process exited${msg.code ? ` (${msg.code})` : ''}]\x1b[0m\r\n`);
				status = 'closed';
				currentSid = null;
				void refreshSessions();
				break;
			case 'error':
				error = msg.msg ?? 'terminal error';
				break;
		}
	}

	function disconnect() {
		// Detaches but the PTY keeps running server-side; it appears in Sessions.
		ws?.close();
		ws = null;
		status = 'idle';
		void refreshSessions();
	}

	async function killSession(sid: string) {
		try {
			await attAction('terminal', 'DELETE', `sessions/${sid}`);
		} catch {
			/* already gone */
		}
		if (sid === currentSid) teardown();
		await refreshSessions();
	}
</script>

<Stack gap={3}>
	<Text role="heading">{node.title ?? 'Terminal'}</Text>

	{#if !supported}
		<Text role="muted">A live terminal isn't supported on this server's platform yet.</Text>
	{:else}
		<!-- Topbar: shell picker + detected shells, connect/disconnect. -->
		<div class="bar">
			<div class="shells">
				{#each shells as sh (sh.path)}
					<button
						class="shell-tab"
						class:active={activeShell === sh.path}
						onclick={() => (activeShell = sh.path)}
						title={sh.path}
					>
						<Icon name="terminal" size={14} />
						{sh.name}
					</button>
				{/each}
			</div>
			<div class="spacer"></div>
			{#if status === 'open'}
				<span class="dot live" title="connected"></span>
				<Button size="sm" variant="warn" onclick={disconnect}>Detach</Button>
			{:else}
				<Button size="sm" variant="accent" disabled={!activeShell || status === 'connecting'} onclick={() => connect(null)}>
					{status === 'connecting' ? 'Connecting…' : 'New session'}
				</Button>
			{/if}
		</div>

		{#if error}<span class="err">{error}</span>{/if}

		<div class="screen" bind:this={host}></div>

		<!-- Reattachable sessions (tmux-like): survive a detach / tab close. -->
		{#if sessions.length}
			<div class="sessions">
				<Text role="label">Running sessions</Text>
				{#each sessions as s (s.id)}
					<div class="session-row">
						<code>{s.shell.split('/').pop()}</code>
						<span class="sid">{s.id.slice(0, 8)}</span>
						{#if s.attached}<span class="dot live" title="attached"></span>{/if}
						<div class="spacer"></div>
						<Button size="sm" variant="ghost" disabled={status === 'open' && currentSid === s.id} onclick={() => connect(s.id)}>
							Attach
						</Button>
						<Button size="sm" variant="danger" onclick={() => killSession(s.id)}>Kill</Button>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</Stack>

<style>
	.bar {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.shells {
		display: flex;
		gap: var(--space-1);
		flex-wrap: wrap;
	}
	.shell-tab {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-2);
		font: inherit;
		font-size: 0.85rem;
		color: var(--muted);
		background: transparent;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.shell-tab.active {
		color: var(--accent-fg);
		background: var(--accent);
		border-color: var(--accent);
	}
	.spacer {
		flex: 1;
	}
	.dot {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: var(--radius-full, 50%);
		background: var(--muted);
	}
	.dot.live {
		background: var(--success);
	}
	.screen {
		width: 100%;
		min-height: 24rem;
		height: 60vh;
		padding: var(--space-2);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		overflow: hidden;
	}
	.sessions {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.session-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.sid {
		font-family: var(--font-mono, monospace);
		font-size: 0.8rem;
		color: var(--muted);
	}
	.err {
		color: var(--danger, crimson);
		font-size: 0.9rem;
	}
	code {
		font-family: var(--font-mono, monospace);
		font-size: 0.85em;
	}
</style>
