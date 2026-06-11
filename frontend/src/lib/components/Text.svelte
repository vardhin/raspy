<script lang="ts">
	// One text primitive, role-driven. Roles map to size/weight/color tokens.
	import type { Snippet } from 'svelte';

	type Role = 'title' | 'heading' | 'body' | 'label' | 'muted';

	let {
		role = 'body',
		as,
		children,
		...rest
	}: {
		role?: Role;
		as?: keyof HTMLElementTagNameMap;
		children: Snippet;
		[key: string]: unknown;
	} = $props();

	const defaultTag: Record<Role, keyof HTMLElementTagNameMap> = {
		title: 'h1',
		heading: 'h2',
		body: 'p',
		label: 'span',
		muted: 'span'
	};
	const tag = $derived(as ?? defaultTag[role]);
</script>

<svelte:element this={tag} class="text {role}" {...rest}>
	{@render children()}
</svelte:element>

<style>
	.text {
		margin: 0;
		color: var(--fg);
		font-weight: var(--font-weight-normal);
		line-height: 1.4;
	}
	.title {
		font-size: 1.6rem;
		font-weight: var(--font-weight-bold);
		letter-spacing: -0.01em;
	}
	.heading {
		font-size: 1.2rem;
		font-weight: var(--font-weight-bold);
	}
	.label {
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
	}
	.muted {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
