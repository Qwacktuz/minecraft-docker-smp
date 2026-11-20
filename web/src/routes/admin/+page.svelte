<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { duration } from '#lib/status.ts';
	import type { Run } from '#lib/runs.ts';
	import { disk, heap, memory, place } from '#lib/vps.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
	let runs: Run[] | string = $derived(data.runs);
	let busy = $state(false);
	let now = $state(Math.floor(Date.now() / 1000));

	const inFlight = $derived(Array.isArray(runs) && runs.some((r) => r.status !== 'completed'));

	onMount(() => {
		// Poll fast while a run is going (or was just requested), slowly otherwise.
		let timer: ReturnType<typeof setTimeout>;
		const poll = async () => {
			now = Math.floor(Date.now() / 1000);
			const response = await fetch('/admin/api/runs');
			if (response.ok) {
				const fresh: Run[] = await response.json();
				const wasInFlight = inFlight;
				runs = fresh;
				// A run just finished: reload the status and backups too.
				if (wasInFlight && !fresh.some((r) => r.status !== 'completed')) await invalidateAll();
			}
			timer = setTimeout(poll, inFlight || busy ? 5_000 : 30_000);
		};
		timer = setTimeout(poll, 5_000);
		return () => clearTimeout(timer);
	});

	function icon(status: string, conclusion: string | null) {
		if (status !== 'completed') return status === 'in_progress' ? '◐' : '○';
		return conclusion === 'success' ? '✓' : conclusion === 'skipped' ? '–' : '✗';
	}
	const when = (iso: string) => new Date(iso).toLocaleString();
	const ago = (seconds: number) => `${duration(now - seconds)} ago`;
	const on = $derived(data.status.state !== 'off');
</script>

<svelte:head>
	<title>Admin · Cactuz SMP</title>
</svelte:head>

<h1>Admin</h1>
<p class="muted">Signed in as {data.admin}</p>

<section class="card">
	<h2><span class="dot {data.status.state}"></span>{on ? `VPS up, ${data.status.players ?? '?'} online` : 'VPS off'}</h2>
	<form
		method="POST"
		use:enhance={() => {
			busy = true;
			return async ({ update }) => {
				await update();
				busy = false;
			};
		}}
		style="display:flex;gap:8px;flex-wrap:wrap"
	>
		<button class="primary" formaction="?/start" disabled={busy || inFlight}>
			{on ? 'Redeploy' : 'Start'}
		</button>
		<button
			class="danger"
			formaction="?/stop"
			disabled={busy || inFlight || !on}
			onclick={(e) => {
				if (!confirm('Back up, then shut down and delete the VPS?')) e.preventDefault();
			}}>Stop</button
		>
	</form>
	{#if form?.message}
		<p class="notice" class:error={form && 'status' in form}>{form.message}</p>
	{/if}
	<p class="muted" style="font-size:0.85rem;margin-bottom:0">
		Runs the GitHub “Server” workflow on <code>main</code>: start takes a few minutes (create the VPS,
		restore the newest backup); stop backs up and verifies before deleting the VPS.
	</p>
</section>

{#if on}
	<section class="card">
		<h2>Hardware</h2>
		{#if data.vps}
			<dl class="specs">
				<dt>Type</dt>
				<dd>Hetzner {data.vps.type.toUpperCase()}</dd>
				<dt>Location</dt>
				<dd>{place(data.vps.location)}</dd>
				<dt>CPU</dt>
				<dd>{data.vps.cpus} vCPU{data.vps.cpu_model ? ` · ${data.vps.cpu_model}` : ''} ({data.vps.arch})</dd>
				<dt>RAM</dt>
				<dd>{memory(data.vps.memory_bytes)}{data.vps.heap ? `, ${heap(data.vps.heap)} of it for the game (heap)` : ''}</dd>
				<dt>Disk</dt>
				<dd>{disk(data.vps.disk_bytes)}</dd>
			</dl>
			<p class="muted" style="font-size:0.85rem;margin-bottom:0">
				Measured on the VPS {ago(data.vps.updated)}, at the end of its start. When Hetzner is sold out,
				<code>bin/server</code> picks another type or location (<code>SERVER_TYPES</code>,
				<code>SERVER_LOCATIONS</code>).
			</p>
		{:else}
			<p class="muted" style="margin-bottom:0">
				Not known yet: the VPS writes it at the end of a start (<code>scripts/publish-status.sh</code>).
			</p>
		{/if}
	</section>
{/if}

<section class="card">
	<h2>Usage</h2>
	{#if !data.usage}
		<p class="muted" style="margin-bottom:0">Could not read the uptime count.</p>
	{:else}
		<div class="stats">
			{#each data.usage as month (month.label)}
				<div class="stat">
					<div class="value">{month.hours.toFixed(1)} h</div>
					<div class="label">
						{month.label}{month.cost !== null ? ` · ≈ €${month.cost.toFixed(2)}` : ''}
						{#if month.countedSince}
							<br />counted since {new Date(month.countedSince * 1000).toLocaleDateString()}
						{/if}
					</div>
				</div>
			{/each}
		</div>
		<p class="muted" style="font-size:0.85rem;margin-bottom:0">
			Hours the VPS existed, counted by the idle watchdog every 5 minutes, whoever started it.
			{#if data.usage[0].cost === null}
				Set <code>HOURLY_PRICE_EUR</code> in <code>web/wrangler.toml</code> to see a cost estimate.
			{:else}
				The cost is hours × <code>HOURLY_PRICE_EUR</code>: a rough estimate, not Hetzner's invoice.
			{/if}
		</p>
	{/if}
</section>

<section class="card">
	<h2>Runs</h2>
	{#if typeof runs === 'string'}
		<p class="notice error">Could not read the runs from GitHub: {runs}</p>
	{:else if runs.length === 0}
		<p class="muted">No runs yet.</p>
	{:else}
		{#each runs as run (run.id)}
			<details open={run.status !== 'completed'} style="margin:6px 0">
				<summary>
					<span class="mono">{icon(run.status, run.conclusion)}</span>
					<strong>{run.action ?? 'run'}</strong>
					<span class="muted">· {when(run.created)}{run.by ? ` · ${run.by}` : ''}</span>
					· <a href={run.url} target="_blank" rel="noreferrer">logs</a>
				</summary>
				{#if run.steps}
					<ul style="list-style:none;padding-left:20px;margin:6px 0">
						{#each run.steps as step}
							<li class:muted={step.status === 'queued'}>
								<span class="mono">{icon(step.status, step.conclusion)}</span>
								{step.name}
							</li>
						{/each}
					</ul>
				{/if}
			</details>
		{/each}
	{/if}
</section>

<section class="card">
	<h2>Backups</h2>
	{#if !data.backups}
		<p class="muted">
			No backup list yet. The VPS writes one at every start and stop
			(<code>scripts/publish-status.sh</code>).
		</p>
	{:else}
		<p class="muted" style="font-size:0.85rem">
			As of {ago(data.backups.updated)}. Hourly backups while the server runs aren't listed until
			the next start or stop.
		</p>
		<div class="table-wrap">
			<table>
				<thead><tr><th>Snapshot</th><th>Time</th><th>Tags</th></tr></thead>
				<tbody>
					{#each data.backups.snapshots.slice(0, 15) as snap (snap.id)}
						<tr>
							<td class="mono">{snap.id.slice(0, 8)}</td>
							<td>{new Date(snap.time * 1000).toLocaleString()}</td>
							<td>{snap.tags.join(', ')}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="muted" style="font-size:0.85rem;margin-bottom:0">
			Restores stay on the laptop: <code>server restore &lt;id&gt;</code>.
		</p>
	{/if}
</section>

<section class="card">
	<h2>Whitelist</h2>
	{#if !data.players}
		<p class="muted" style="margin-bottom:0">
			No list yet. The VPS writes it at every start and stop (<code>scripts/publish-status.sh</code>).
		</p>
	{:else}
		<p class="muted" style="font-size:0.85rem">
			{data.players.players.filter((p) => p.whitelisted).length} whitelisted, as of {ago(data.players.updated)}.
		</p>
		<div class="table-wrap">
			<table>
				<thead><tr><th>Player</th><th>Role</th></tr></thead>
				<tbody>
					{#each data.players.players as player (player.uuid)}
						<tr>
							<td>
								<span class="player">
									<img
										src="https://mc-heads.net/avatar/{player.uuid}/20"
										alt=""
										width="20"
										height="20"
										loading="lazy"
									/>
									{player.name}
								</span>
							</td>
							<td>
								{#if player.op_level}
									<span class="badge op">op {player.op_level}</span>
								{/if}
								{#if !player.whitelisted}
									<span class="badge">not whitelisted</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="muted" style="font-size:0.85rem;margin-bottom:0">
			The list comes from <code>MC_WHITELIST</code> in <code>secrets/app.enc.env</code>: every start
			replaces the server's whitelist with it, so <code>/whitelist add</code> in game only lasts until
			the next start.
		</p>
	{/if}
</section>
