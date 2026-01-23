<script lang="ts">
  import { feeds, removeFeed, unreadByFeed } from "../lib/store";

  async function confirmRemove(id: number, title: string) {
    if (confirm(`Unsubscribe from “${title}”? Its items will be removed.`)) {
      await removeFeed(id);
    }
  }
</script>

<nav class="feeds">
  <h2>Feeds</h2>
  {#if $feeds.length === 0}
    <p class="empty">No feeds yet.</p>
  {:else}
    <ul>
      {#each $feeds as feed (feed.id)}
        <li>
          <div class="feed-row">
            <span class="feed-title" title={feed.url}>{feed.title}</span>
            {#if $unreadByFeed.get(feed.id)}
              <span class="badge">{$unreadByFeed.get(feed.id)}</span>
            {/if}
            <button
              class="remove"
              title="Unsubscribe"
              on:click={() => confirmRemove(feed.id, feed.title)}
            >
              ×
            </button>
          </div>
          {#if feed.last_error}
            <span class="feed-error" title={feed.last_error}>⚠ fetch error</span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</nav>

<style>
  .feeds h2 {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin: 0 0 0.5rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    padding: 0.3rem 0;
  }
  .feed-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .feed-title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.92rem;
  }
  .badge {
    flex-shrink: 0;
    min-width: 1.25rem;
    padding: 0 0.35rem;
    border-radius: 999px;
    background: var(--surface-alt);
    color: var(--text-soft);
    font-size: 0.72rem;
    font-weight: 600;
    line-height: 1.25rem;
    text-align: center;
  }
  .remove {
    border: none;
    background: none;
    color: var(--text-muted);
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    padding: 0 0.25rem;
    border-radius: 4px;
  }
  .remove:hover {
    color: var(--danger);
    background: var(--surface-alt);
  }
  .feed-error {
    display: block;
    font-size: 0.75rem;
    color: var(--danger);
  }
  .empty {
    color: var(--text-muted);
    font-size: 0.9rem;
  }
</style>
