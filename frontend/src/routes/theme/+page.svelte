<script lang="ts">
	// Theme app: a full page for choosing the color palette and concept. The
	// picker is frontend-only (themes never come from the backend), so it lives
	// at a fixed /theme route rather than under /a/<id> like manifest apps.
	import { Stack, Text, ThemePicker, WallpaperPicker, Surface } from '$lib/components';
	import { theme } from '$lib/themes/store.svelte';
</script>

<Stack gap={5}>
	<Stack gap={1}>
		<Text role="title">Theme</Text>
		<Text role="muted">
			Pick a color palette and a concept (form & material). They compose freely —
			currently <b>{theme.color.name}</b> × <b>{theme.concept.name}</b>. Changes apply
			instantly and are remembered on this device.
		</Text>
	</Stack>

	<Surface level={2}>
		<WallpaperPicker />
	</Surface>

	<ThemePicker />
</Stack>
