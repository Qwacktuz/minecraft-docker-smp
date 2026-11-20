<script lang="ts">
	import { boards } from '#lib/leaderboard.ts';
	import { duration } from '#lib/status.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const shown = $derived(data.leaderboard ? boards(data.leaderboard) : []);
	const ago = $derived(
		data.leaderboard ? `${duration(Math.floor(Date.now() / 1000) - data.leaderboard.updated)} ago` : ''
	);
</script>

<svelte:head>
	<title>Leaderboard · Cactuz SMP</title>
</svelte:head>

<h1>Leaderboard</h1>
{#if !data.leaderboard || shown.length === 0}
	<p class="muted">
		No numbers yet. They're published each time the server starts or stops.
	</p>
{:else}
	<p class="muted">
		Updated {ago}, at the server's last start or stop. Whitelisted players only.
	</p>
	<div class="boards">
		{#each shown as board (board.stat)}
			<section class="card">
				<h2>{board.title}</h2>
				<ol class="ranking">
					{#each board.entries as entry (entry.uuid)}
						<li class:first={entry.rank === 1}>
							<span class="rank">{entry.rank}</span>
							<span class="player">
								<img
									src="https://mc-heads.net/avatar/{entry.uuid}/20"
									alt=""
									width="20"
									height="20"
									loading="lazy"
								/>
								{entry.name}
							</span>
							<span class="value">{board.format(entry.value)}</span>
						</li>
					{/each}
				</ol>
			</section>
		{/each}
	</div>
	<p class="muted" style="font-size:0.85rem">
		From the game's own statistics; blocks placed come from the grief log (Ledger), without
		anything an op rolled back. Distance counts every way of moving.
	</p>
{/if}
