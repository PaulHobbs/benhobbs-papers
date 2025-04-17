<script>
  export let data;
</script>

<div class="container mx-auto p-4">
  <h1 class="text-3xl font-bold mb-6">Generated Paper Explorations</h1>
  
  {#each data.sites as site}
    <div class="mb-4 p-4 border rounded hover:bg-gray-50">
      <a
        href={site.path}
        class="text-blue-600 hover:text-blue-800 text-lg font-medium"
        target="_blank"
      >
        {site.paper.replace(/_/g, ' ')}
      </a>
      <p class="text-sm text-gray-500 mt-1">
        Generated: {new Date(site.generated).toLocaleDateString()}
      </p>
    </div>
  {:else}
    <p class="text-gray-500">No generated sites found</p>
  {/each}
</div>
