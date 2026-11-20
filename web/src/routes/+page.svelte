<script lang="ts">
	import { onMount } from 'svelte';
	import { duration, type Status } from '#lib/status.ts';
	import { place, summary } from '#lib/vps.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let polled: Status | null = $state(null);
	const status = $derived(polled ?? data.status);
	let now = $state(Math.floor(Date.now() / 1000));

	onMount(() => {
		const tick = setInterval(() => (now = Math.floor(Date.now() / 1000)), 15_000);
		const poll = setInterval(async () => {
			const response = await fetch('/api/status');
			if (response.ok) polled = await response.json();
		}, 30_000);
		return () => {
			clearInterval(tick);
			clearInterval(poll);
		};
	});

	const label = $derived(
		status.state === 'online' ? 'Online' : status.state === 'starting' ? 'Starting up' : 'Offline'
	);
</script>

<svelte:head>
	<title>Cactuz SMP</title>
</svelte:head>

<h1><span class="dot {status.state}"></span>{label}</h1>
<p class="muted">
	{#if status.state === 'off'}
		The server is asleep. It starts on demand; ask an admin, or use the admin page if you are one.
	{:else if status.state === 'starting'}
		The VPS is up, but the game isn't answering yet. Give it a minute.
	{:else}
		Join with <code>{data.host}</code> (Fabric, whitelist only).
	{/if}
</p>

{#if status.state !== 'off'}
	<section class="card">
		<div class="stats">
			<div class="stat">
				<div class="value">{status.players ?? '–'}</div>
				<div class="label">players online</div>
			</div>
			<div class="stat">
				<div class="value">{status.upSince ? duration(now - status.upSince) : '–'}</div>
				<div class="label">up for</div>
			</div>
			<div class="stat">
				<div class="value">
					{#if status.players}
						–
					{:else if status.stopAt}
						{duration(status.stopAt - now)}
					{:else}
						–
					{/if}
				</div>
				<div class="label">
					{#if status.players}
						no auto-stop while someone plays
					{:else}
						until auto-stop {status.stopReason === 'max-uptime' ? `(${data.maxDays}-day cap)` : ''}
					{/if}
				</div>
			</div>
		</div>
		{#if status.players}
			<div class="online">
				<h2>Online now</h2>
				{#if status.names.length}
					<ul class="names">
						{#each status.names as name (name)}
							<li>
								<img src="https://mc-heads.net/avatar/{encodeURIComponent(name)}/24" alt="" width="24" height="24" loading="lazy" />
								{name}
							</li>
						{/each}
					</ul>
				{/if}
				{#if status.names.length < status.players}
					<p class="muted" style="font-size:0.85rem;margin:8px 0 0">
						{status.names.length ? `and ${status.players - status.names.length} more` : `${status.players} online`}
						(the server doesn't name everyone)
					</p>
				{/if}
			</div>
		{/if}
		{#if data.hardware}
			<p class="hardware">
				{summary(data.hardware)} · {place(data.hardware.location)}
			</p>
		{/if}
		<p class="muted" style="margin-bottom:0;font-size:0.85rem">
			It stops itself after {data.idleMinutes / 60} hours with nobody online (bots count) or after
			{data.maxDays} days, and backs up first.
		</p>
	</section>
{/if}

<section class="card">
	<h2>Download the world</h2>
	<p>
		A copy of the world without player data, updated each time the server stops. Good for
		testing redstone in singleplayer.
	</p>
	<a class="button primary" href={data.worldUrl}>Download world.zip</a>
</section>
