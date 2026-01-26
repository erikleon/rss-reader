<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import AddFeed from "./components/AddFeed.svelte";
  import ImportOpml from "./components/ImportOpml.svelte";
  import FeedSidebar from "./components/FeedSidebar.svelte";
  import RefreshButton from "./components/RefreshButton.svelte";
  import DaySection from "./components/DaySection.svelte";
  import {
    dayGroups,
    days,
    error,
    loadFeeds,
    loadItems,
    loadingItems,
    markAllRead,
    markReadOnScroll,
    openSelected,
    searchQuery,
    selectNext,
    selectPrev,
    toggleSelectedRead,
    unreadOnly,
  } from "./lib/store";

  // Debounced search input.
  let searchText = "";
  let searchTimer: ReturnType<typeof setTimeout>;
  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchQuery.set(searchText.trim());
      loadItems();
    }, 250);
  }
  function clearSearch() {
    clearTimeout(searchTimer);
    searchText = "";
    searchQuery.set("");
    loadItems();
  }

  onMount(async () => {
    await Promise.all([loadFeeds(), loadItems()]);
  });

  // Reader keyboard shortcuts, ignored while typing in a field.
  function onKeydown(e: KeyboardEvent) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable))
      return;
    const handler: Record<string, () => void> = {
      j: selectNext,
      k: selectPrev,
      o: openSelected,
      m: toggleSelectedRead,
    };
    const fn = handler[e.key];
    if (fn) {
      e.preventDefault();
      fn();
    }
  }
  onMount(() => {
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  });

  // The backend auto-refreshes feeds on its own schedule; poll periodically so
  // newly fetched items surface without a manual reload.
  const POLL_MS = 5 * 60 * 1000;
  const poll = setInterval(() => {
    loadFeeds();
    loadItems();
  }, POLL_MS);
  onDestroy(() => clearInterval(poll));

  // Reload items whenever the unread filter changes.
  function onToggleUnread() {
    unreadOnly.update((v) => !v);
    loadItems();
  }

  function loadOlder() {
    days.update((d) => d + 30);
    loadItems();
  }
</script>

<div class="layout">
  <aside class="sidebar">
    <h1 class="brand">RSS Reader</h1>
    <AddFeed />
    <FeedSidebar />
    <ImportOpml />
  </aside>

  <main class="content">
    <div class="searchbar">
      <input
        type="search"
        placeholder="Search items…"
        bind:value={searchText}
        on:input={onSearchInput}
      />
      {#if $searchQuery}
        <button class="link" on:click={clearSearch}>Clear</button>
      {/if}
    </div>

    <header class="toolbar">
      <RefreshButton />
      <div class="toolbar-right">
        <label class="filter">
          <input
            type="checkbox"
            checked={$unreadOnly}
            on:change={onToggleUnread}
          />
          Unread only
        </label>
        <label class="filter">
          <input
            type="checkbox"
            checked={$markReadOnScroll}
            on:change={() => markReadOnScroll.update((v) => !v)}
          />
          Mark read on scroll
        </label>
        <button class="link" on:click={markAllRead}>Mark all read</button>
        <span class="kbd-hint" title="j/k move · o open · m toggle read">⌨</span>
      </div>
    </header>

    {#if $error}
      <p class="error">{$error}</p>
    {/if}

    {#if $loadingItems && $dayGroups.length === 0}
      <p class="muted">Loading…</p>
    {:else if $dayGroups.length === 0}
      <p class="muted">
        {#if $searchQuery}
          No items match “{$searchQuery}”.
        {:else}
          No items to show. Add a feed and hit Refresh to pull the latest.
        {/if}
      </p>
    {:else}
      {#each $dayGroups as group (group.key)}
        <DaySection {group} />
      {/each}
      {#if !$searchQuery}
        <div class="load-older">
          <button class="link" on:click={loadOlder}>Load older</button>
        </div>
      {/if}
    {/if}
  </main>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    min-height: 100vh;
    max-width: 1100px;
    margin: 0 auto;
  }
  .sidebar {
    padding: 1.5rem 1.25rem;
    border-right: 1px solid var(--border);
    position: sticky;
    top: 0;
    align-self: start;
    height: 100vh;
    overflow-y: auto;
  }
  .brand {
    font-size: 1.1rem;
    margin: 0 0 1rem;
  }
  .sidebar :global(.add-feed) {
    margin-bottom: 1.5rem;
  }
  .content {
    padding: 1.5rem 2rem 4rem;
    min-width: 0;
  }
  .searchbar {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 1rem;
  }
  .searchbar input {
    flex: 1;
    min-width: 0;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font: inherit;
    background: var(--surface);
    color: var(--text);
  }
  .searchbar input:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
  }
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .filter {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.88rem;
    color: var(--text-soft);
    cursor: pointer;
  }
  .link {
    border: none;
    background: none;
    color: var(--accent);
    font: inherit;
    font-size: 0.88rem;
    cursor: pointer;
    padding: 0;
  }
  .link:hover {
    text-decoration: underline;
  }
  .kbd-hint {
    color: var(--text-muted);
    cursor: help;
    font-size: 0.95rem;
  }
  .error {
    background: var(--danger-bg);
    color: var(--danger);
    padding: 0.6rem 0.85rem;
    border-radius: 6px;
    font-size: 0.9rem;
    margin: 0 0 1rem;
  }
  .muted {
    color: var(--text-muted);
  }
  .load-older {
    text-align: center;
    margin-top: 1rem;
  }

  @media (max-width: 720px) {
    .layout {
      grid-template-columns: 1fr;
    }
    .sidebar {
      position: static;
      height: auto;
      border-right: none;
      border-bottom: 1px solid var(--border);
    }
  }
</style>
