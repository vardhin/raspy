<script lang="ts">
	import { Surface, Button, Text, Stack, Field, Badge, ThemePicker } from '$lib/components';
	import { theme } from '$lib/themes/store.svelte';

	let todo = $state('');
	let agree = $state(false);
	let items = $state(['Wire up the spine', 'Add the todo attachment', 'Ship the APK']);

	function add() {
		const t = todo.trim();
		if (t) {
			items = [...items, t];
			todo = '';
		}
	}
</script>

<div class="page">
	<Stack gap={5}>
		<Stack gap={2}>
			<Text role="title">Raspy — Theme Lab</Text>
			<Text role="muted">
				Every component reads only design tokens. Pick any color × any concept — the whole UI
				re-skins live. Currently:
				<Badge variant="accent">{theme.color.name}</Badge>
				×
				<Badge variant="info">{theme.concept.name}</Badge>
			</Text>
		</Stack>

		<Surface level={2}>
			<Stack gap={3}>
				<Text role="label">Theme</Text>
				<ThemePicker />
			</Stack>
		</Surface>

		<Stack direction="row" gap={4} wrap>
			<Surface>
				<Stack gap={3}>
					<Text role="heading">Buttons</Text>
					<Stack direction="row" gap={2} wrap>
						<Button variant="accent">Accent</Button>
						<Button variant="neutral">Neutral</Button>
						<Button variant="ghost">Ghost</Button>
					</Stack>
					<Stack direction="row" gap={2} wrap>
						<Button variant="success">Success</Button>
						<Button variant="warn">Warn</Button>
						<Button variant="danger">Danger</Button>
					</Stack>
				</Stack>
			</Surface>

			<Surface>
				<Stack gap={3}>
					<Text role="heading">Status</Text>
					<Stack direction="row" gap={2} wrap>
						<Badge>Neutral</Badge>
						<Badge variant="success">Online</Badge>
						<Badge variant="warn">Pending</Badge>
						<Badge variant="danger">Error</Badge>
						<Badge variant="info">Info</Badge>
					</Stack>
				</Stack>
			</Surface>
		</Stack>

		<Surface>
			<Stack gap={3}>
				<Text role="heading">Todo (component demo)</Text>
				<Stack direction="row" gap={2} align="end">
					<div style="flex:1">
						<Field label="New item" placeholder="What needs doing?" bind:value={todo} />
					</div>
					<Button onclick={add}>Add</Button>
				</Stack>
				<Stack gap={2}>
					{#each items as item (item)}
						<Surface interactive>
							<Text role="body">{item}</Text>
						</Surface>
					{/each}
				</Stack>
				<Field type="checkbox" label="I read plan/45-theming.md" bind:value={agree} />
			</Stack>
		</Surface>

		<Surface>
			<Stack gap={3}>
				<Text role="heading">Form controls</Text>
				<Field label="Server address" placeholder="https://pi.example.com" />
				<Field
					type="select"
					label="Transport"
					options={[
						{ value: 'lan', label: 'LAN' },
						{ value: 'cf', label: 'Cloudflare Tunnel' },
						{ value: 'ts', label: 'Tailscale' }
					]}
				/>
				<Field type="textarea" label="Notes" placeholder="Anything…" />
			</Stack>
		</Surface>
	</Stack>
</div>

<style>
	.page {
		max-width: 880px;
		margin: 0 auto;
		padding: var(--space-6) var(--space-4);
	}
</style>
