<script lang="ts">
  import { page } from '$app/stores';
  import { derived } from 'svelte/store';
  import Navbar from '$lib/components/Navbar.svelte';

  const siteId = derived(page, ($page) => $page.params.siteid);
  const iframeSrc = derived(siteId, ($siteId) => `/sites/${$siteId}.html`); // Static files are served from the root
</script>

<svelte:head>
  <title>Site: {$siteId}</title>
</svelte:head>

<Navbar />

<div class="site-container">
  <iframe
    src={$iframeSrc}
    title="Site {$siteId}"
    width="100%"
    height="800px"
    frameborder="0"
  ></iframe>
</div>

<style>
  .site-container {
    width: 100%;
    height: calc(100vh - 50px); /* Adjust height based on potential navbar */
    overflow: hidden;
  }
  iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
</style>