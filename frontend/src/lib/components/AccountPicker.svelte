<script lang="ts">
	// A generic account picker: a list of accounts (avatar initial, name, role
	// badge) with a selected highlight. Token-only and decoupled — the parent passes
	// the accounts and owns the selection. Used by the dropbox and chat apps to pick
	// who to send to / talk with.
	import Text from './Text.svelte';
	import Badge from './Badge.svelte';

	type Account = {
		username: string;
		role?: 'admin' | 'child';
		subtitle?: string;
		/** When false, the row is shown but cannot be selected (no published key). */
		disabled?: boolean;
	};

	let {
		accounts,
		selected = $bindable(null),
		onselect
	}: {
		accounts: Account[];
		selected?: string | null;
		onselect?: (username: string) => void;
	} = $props();

	function pick(a: Account) {
		if (a.disabled) return;
		selected = a.username;
		onselect?.(a.username);
	}

	function initial(name: string): string {
		return (name.trim()[0] ?? '?').toUpperCase();
	}
</script>

<div class="picker" role="listbox" aria-label="Accounts">
	{#each accounts as a (a.username)}
		<button
			type="button"
			class="account"
			class:selected={selected === a.username}
			class:disabled={a.disabled}
			role="option"
			aria-selected={selected === a.username}
			aria-disabled={a.disabled}
			disabled={a.disabled}
			onclick={() => pick(a)}
		>
			<span class="avatar" aria-hidden="true">{initial(a.username)}</span>
			<span class="meta">
				<Text role="label">{a.username}</Text>
				{#if a.disabled}<Text role="muted">Hasn't set up messaging yet</Text>
				{:else if a.subtitle}<Text role="muted">{a.subtitle}</Text>{/if}
			</span>
			{#if a.role}<Badge variant={a.role === 'admin' ? 'accent' : 'neutral'}>{a.role}</Badge>{/if}
		</button>
	{/each}
	{#if accounts.length === 0}
		<Text role="muted">No other accounts yet.</Text>
	{/if}
</div>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		width: 100%;
	}
	.account {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-md);
		border: var(--border-width) solid transparent;
		background: transparent;
		color: var(--fg);
		cursor: pointer;
		text-align: left;
		transition: background var(--motion-fast) var(--motion-ease);
	}
	.account:hover {
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 60%), transparent);
	}
	.account.selected {
		background: color-mix(in srgb, var(--accent) 18%, transparent);
		border-color: var(--border-color);
	}
	.account.disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.account.disabled:hover {
		background: transparent;
	}
	.avatar {
		flex: none;
		width: 2.2rem;
		height: 2.2rem;
		display: grid;
		place-items: center;
		border-radius: 50%;
		background: color-mix(in srgb, var(--accent) 30%, var(--surface-2));
		font-weight: var(--font-weight-bold);
	}
	.meta {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
</style>
