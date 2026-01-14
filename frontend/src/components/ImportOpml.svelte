<script lang="ts">
  import { importOpml, importStatus } from "../lib/store";

  let input: HTMLInputElement;

  async function onChange() {
    const file = input.files?.[0];
    if (!file) return;
    const xml = await file.text();
    await importOpml(xml);
    input.value = ""; // allow re-importing the same file
  }
</script>

<div class="import">
  <button type="button" on:click={() => input.click()}>Import OPML</button>
  <input
    bind:this={input}
    type="file"
    accept=".opml,.xml,text/xml,application/xml"
    on:change={onChange}
    hidden
  />
  {#if $importStatus}
    <p class="status">{$importStatus}</p>
  {/if}
</div>

<style>
  .import {
    margin-top: 0.75rem;
  }
  button {
    width: 100%;
    padding: 0.45rem 0.6rem;
    border: 1px dashed var(--border);
    border-radius: 6px;
    background: none;
    color: var(--text-soft);
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }
  button:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  .status {
    margin: 0.4rem 0 0;
    font-size: 0.78rem;
    color: var(--text-muted);
  }
</style>
