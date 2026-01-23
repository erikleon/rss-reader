<script lang="ts">
  import { formatAbsolute, formatRelative } from "../lib/datetime";
  import { feedTitles, toggleRead } from "../lib/store";
  import type { Item } from "../lib/types";

  export let item: Item;
  export let selected = false;

  let el: HTMLElement;
  $: source = $feedTitles.get(item.feed_id) ?? "";
  $: if (selected && el) el.scrollIntoView({ block: "nearest" });

  function open() {
    // Opening the article marks it read (common reader behavior).
    if (!item.read) toggleRead(item);
  }
</script>

<article class="item" class:read={item.read} class:selected bind:this={el}>
  <button
    class="toggle"
    title={item.read ? "Mark unread" : "Mark read"}
    on:click={() => toggleRead(item)}
  >
    {item.read ? "○" : "●"}
  </button>

  <div class="body">
    <h3 class="title">
      {#if item.link}
        <a href={item.link} target="_blank" rel="noopener noreferrer" on:click={open}>
          {item.title}
        </a>
      {:else}
        {item.title}
      {/if}
    </h3>
    <div class="meta">
      <span class="source">{source}</span>
      <span class="dot">·</span>
      <time title={formatAbsolute(item.published_at)}>
        {formatRelative(item.published_at)}
      </time>
    </div>
    {#if item.summary}
      <p class="summary">{item.summary}</p>
    {/if}
  </div>
</article>

<style>
  .item {
    display: flex;
    gap: 0.6rem;
    padding: 0.85rem 0;
    border-bottom: 1px solid var(--border);
  }
  .item.read {
    opacity: 0.55;
  }
  .item.selected {
    box-shadow: inset 3px 0 0 var(--accent);
    background: var(--surface-alt);
  }
  .toggle {
    border: none;
    background: none;
    color: var(--accent);
    font-size: 0.8rem;
    line-height: 1.6;
    cursor: pointer;
    padding: 0;
    height: fit-content;
  }
  .item.read .toggle {
    color: var(--text-muted);
  }
  .body {
    flex: 1;
    min-width: 0;
  }
  .title {
    margin: 0 0 0.2rem;
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.35;
  }
  .title a {
    color: var(--text);
    text-decoration: none;
  }
  .title a:hover {
    color: var(--accent);
    text-decoration: underline;
  }
  .meta {
    font-size: 0.8rem;
    color: var(--text-muted);
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .source {
    font-weight: 500;
  }
  .summary {
    margin: 0.35rem 0 0;
    font-size: 0.9rem;
    color: var(--text-soft);
    line-height: 1.5;
  }
</style>
