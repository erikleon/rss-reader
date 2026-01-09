<script lang="ts">
  import { addFeed } from "../lib/store";

  let url = "";
  let busy = false;
  let localError: string | null = null;

  async function submit() {
    const value = url.trim();
    if (!value || busy) return;
    busy = true;
    localError = null;
    try {
      await addFeed(value);
      url = ""; // clear only on success
    } catch (e) {
      localError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<form class="add-feed" on:submit|preventDefault={submit}>
  <input
    type="url"
    placeholder="Add feed URL…"
    bind:value={url}
    disabled={busy}
    aria-label="Feed URL"
  />
  <button type="submit" disabled={busy || !url.trim()}>
    {busy ? "Adding…" : "Add"}
  </button>
</form>
{#if localError}
  <p class="add-error">{localError}</p>
{/if}

<style>
  .add-feed {
    display: flex;
    gap: 0.5rem;
  }
  input {
    flex: 1;
    min-width: 0;
    padding: 0.5rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font: inherit;
    background: var(--surface);
    color: var(--text);
  }
  input:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }
  button {
    padding: 0.5rem 0.85rem;
    border: none;
    border-radius: 6px;
    background: var(--accent);
    color: white;
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .add-error {
    margin: 0.5rem 0 0;
    color: var(--danger);
    font-size: 0.85rem;
  }
</style>
