import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Static adapter: the spine serves the built bundle as plain files —
			// no Node runtime on the Pi. SPA fallback so client-side routing works
			// for /a/[name] attachment views. See plan/40-frontend.md.
			adapter: adapter({ fallback: 'index.html' })
		})
	],

	build: {
		// libsodium-wrappers-sumo (Argon2id WASM) is ~530 kB and now lives in its
		// own lazily-loaded chunk (see src/lib/crypto/sodium.ts). It loads only on
		// first crypto use, so the size is acceptable; bump the warning limit past
		// it so the threshold still catches genuinely unexpected large chunks.
		chunkSizeWarningLimit: 600
	}
});
