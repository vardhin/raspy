<script lang="ts">
	// Token-only loading spinner. A rotating ring whose active arc uses --accent;
	// size in px. Honors prefers-reduced-motion (handled globally in app.css).
	let {
		size = 22,
		label = 'Loading'
	}: {
		size?: number;
		label?: string;
	} = $props();
</script>

<span
	class="spinner"
	role="status"
	aria-label={label}
	style:width="{size}px"
	style:height="{size}px"
	style:border-width="{Math.max(2, Math.round(size / 9))}px"
></span>

<style>
	.spinner {
		display: inline-block;
		flex: none;
		border-style: solid;
		border-color: color-mix(in srgb, var(--muted) 35%, transparent);
		border-top-color: var(--accent);
		border-radius: var(--radius-full);
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
