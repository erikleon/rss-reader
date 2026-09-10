<script lang="ts">
  import { formatAbsolute } from "../lib/datetime";
  import {
    closeReader,
    feedTitles,
    openReader,
    readerArticle,
    readerItem,
    readerLoading,
  } from "../lib/store";

  $: item = $readerItem;
  $: article = $readerArticle;
  $: source = item ? ($feedTitles.get(item.feed_id) ?? "") : "";

  // Escape is handled once, on the window, in App.svelte. A second listener
  // here would only fire when the overlay itself has focus, which is exactly
  // the case where the global one already works.
</script>

{#if item}
  <!--
    The whole point of the pane is that there is nothing else on it: no sidebar,
    no unread counts, no next-item rail. Everything that competes for attention
    lives on the list behind it, and Escape gets you back there.
  -->
  <div
    class="overlay"
    role="dialog"
    aria-modal="true"
    aria-label={item.title}
  >
    <div class="bar">
      <button class="link" on:click={closeReader}>← Back</button>
      <div class="bar-right">
        {#if article && !article.error}
          <span class="muted">{article.word_count} words</span>
        {/if}
        <button class="link" on:click={() => item && openReader(item, true)}>
          Re-fetch
        </button>
        {#if item.link}
          <a class="link" href={item.link} target="_blank" rel="noreferrer noopener">
            Original ↗
          </a>
        {/if}
      </div>
    </div>

    <article class="reading">
      <h1>{article?.title || item.title}</h1>
      <p class="byline">
        {source}
        <span aria-hidden="true">·</span>
        <time datetime={item.published_at}>{formatAbsolute(item.published_at)}</time>
      </p>

      {#if $readerLoading}
        <p class="muted">Fetching the page…</p>
      {:else if article?.error}
        <p class="unreadable">This page could not be read here.</p>
        <p class="muted">{article.error}</p>
        {#if item.link}
          <p>
            <a href={item.link} target="_blank" rel="noreferrer noopener">
              Open the original ↗
            </a>
          </p>
        {/if}
      {:else if article?.html}
        <!--
          Sanitised on the server, in extract.py, against an allowlist of tags
          and attributes. That is the only reason this is safe to inject: the
          bytes came from a page a stranger wrote, and nothing in the browser
          is checking them again.
        -->
        {@html article.html}
      {:else}
        <p class="muted">Nothing to show.</p>
      {/if}
    </article>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 20;
    overflow-y: auto;
    background: var(--bg);
  }
  .bar {
    position: sticky;
    top: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1.25rem;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
  }
  .bar-right {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  /* A measure, not a width. Long lines are the thing a reader view exists to
     fix, so this stays in the 60-to-75-character range at the body size. */
  .reading {
    max-width: 38rem;
    margin: 0 auto;
    padding: 2.5rem 1.25rem 6rem;
    font-size: 1.0625rem;
    line-height: 1.65;
  }
  .reading h1 {
    font-size: 1.75rem;
    line-height: 1.25;
    margin: 0 0 0.5rem;
  }
  .byline {
    margin: 0 0 2rem;
    color: var(--text-muted);
    font-size: 0.875rem;
  }
  .unreadable {
    color: var(--danger);
  }
  .muted {
    color: var(--text-muted);
  }

  /* Everything below styles server-sanitised HTML, so it is :global. The
     allowlist in extract.py is the list of tags that can turn up here. */
  .reading :global(p),
  .reading :global(ul),
  .reading :global(ol),
  .reading :global(blockquote),
  .reading :global(pre),
  .reading :global(figure),
  .reading :global(table) {
    margin: 0 0 1.25rem;
  }
  .reading :global(h2),
  .reading :global(h3),
  .reading :global(h4) {
    line-height: 1.3;
    margin: 2rem 0 0.75rem;
  }
  .reading :global(img) {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.5rem auto;
  }
  .reading :global(figure) {
    margin-inline: 0;
  }
  .reading :global(figcaption) {
    font-size: 0.85rem;
    color: var(--text-muted);
    text-align: center;
  }
  .reading :global(blockquote) {
    padding-left: 1rem;
    border-left: 3px solid var(--border);
    color: var(--text-soft);
  }
  .reading :global(pre) {
    background: var(--surface-alt);
    padding: 0.9rem 1rem;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.9rem;
    line-height: 1.5;
  }
  .reading :global(code) {
    font-size: 0.9em;
  }
  .reading :global(:not(pre) > code) {
    background: var(--surface-alt);
    padding: 0.1em 0.35em;
    border-radius: 4px;
  }
  .reading :global(table) {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  .reading :global(th),
  .reading :global(td) {
    border: 1px solid var(--border);
    padding: 0.4rem 0.6rem;
    text-align: left;
  }
  .reading :global(hr) {
    border: 0;
    border-top: 1px solid var(--border);
    margin: 2rem 0;
  }
  .reading :global(a) {
    color: var(--accent);
  }
</style>
