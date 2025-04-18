<script lang="ts">
  interface PaperSite {
    paper: string;
    path: string;
    generated: string;
  }

  export let data: { sites?: PaperSite[] };

  // Format paper titles for display
  const formatTitle = (title: string) =>
    title.replace(/_/g, ' ').replace(/(\d{4})_/g, '$1 ');

  // Date formatting utility
  const formatDate = (isoString: string) =>
    new Date(isoString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
</script>

<style>
  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem 1rem;
  }

  header {
    text-align: center;
    margin-bottom: 3rem;
  }

  h1 {
    font-size: 2.5rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: #1a1a1a;
  }

  .subtitle {
    color: #666;
    font-size: 1.1rem;
    margin-bottom: 2rem;
  }

  .grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  }

  .card {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    padding: 1.5rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }

  .card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0,0,0,0.15);
  }

  .paper-title {
    font-size: 1.1rem;
    font-weight: 500;
    color: #0066cc;
    text-decoration: none;
    display: block;
    margin-bottom: 1rem;
  }

  .paper-title:hover {
    text-decoration: underline;
  }

  .date {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #666;
    font-size: 0.9rem;
  }

  .date svg {
    flex-shrink: 0;
  }

  .empty-state {
    text-align: center;
    padding: 4rem 0;
    color: #666;
  }

  .empty-state svg {
    width: 64px;
    height: 64px;
    margin-bottom: 1rem;
    opacity: 0.8;
  }
</style>

<div class="container">
  <header>
    <h1>Research Paper Explorer</h1>
    <p class="subtitle">Explore automatically generated paper analyses</p>
  </header>

  {#if data?.sites?.length}
    <div class="grid">
      {#each data.sites as site}
        <div class="card">
          <a href={site.path} class="paper-title" target="_blank" rel="noopener">
            {site.title}
          </a>
          <div class="date">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <p>No research papers available</p>
    </div>
  {/if}
</div>
