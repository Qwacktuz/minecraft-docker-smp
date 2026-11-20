<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { duration } from '#lib/status.ts';
	import type { Run } from '#lib/runs.ts';
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
