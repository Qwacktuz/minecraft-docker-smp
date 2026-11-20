<script lang="ts">
	import '#lib/app.css';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href="/icon.png" />
</svelte:head>

<header>
	<a href="/" class="brand">Cactuz SMP</a>
	<nav><a href="/admin">Admin</a></nav>
</header>
<main>
	{@render children()}
</main>
