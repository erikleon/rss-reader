<script lang="ts">
  import type { DayGroup } from "../lib/types";
  import ItemRow from "./ItemRow.svelte";

  export let group: DayGroup;
</script>

<section class="day">
  <h2 class="day-header">{group.label}</h2>
  {#each group.items as item (item.id)}
    <ItemRow {item} />
  {/each}
</section>

<style>
  .day {
    margin-bottom: 1.75rem;
  }
  .day-header {
    position: sticky;
    top: 0;
    margin: 0 0 0.25rem;
    padding: 0.5rem 0;
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text);
    background: var(--bg);
    border-bottom: 2px solid var(--border);
  }
</style>
