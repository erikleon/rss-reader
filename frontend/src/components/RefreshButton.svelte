<script lang="ts">
  import { refresh, refreshing, lastRefresh } from "../lib/store";
</script>

<div class="refresh">
  <button on:click={refresh} disabled={$refreshing}>
    {$refreshing ? "Refreshing…" : "↻ Refresh"}
  </button>
  {#if $lastRefresh}
    <span class="status">{$lastRefresh}</span>
  {/if}
</div>

<style>
  .refresh {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  button {
    padding: 0.5rem 0.9rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }
  button:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }
  button:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .status {
    font-size: 0.85rem;
    color: var(--text-muted);
  }
</style>
