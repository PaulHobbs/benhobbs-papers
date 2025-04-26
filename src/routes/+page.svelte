<script lang="ts">
  interface PaperSite {
    paper: string;
    path: string;
    title: string;
    generated: string;
    authors: string[];
    pdf_site: string;
    pdf_title: string;
    publication_date?: string;
  }

  export let data: { sites: PaperSite[] };

  // Format authors with Wikipedia links
  const formatAuthors = (authors?: string[]) => {
    if (!authors?.length || authors.every((a) => a === "Unknown author")) {
      return "Authors: Not specified";
    }

    return `Authors: ${authors
      .map((author) =>
        author !== "Unknown author"
          ? `<a href="https://scholar.google.com/scholar?q=${encodeURIComponent(author)}"
            target="_blank"
            rel="noopener"
            class="author-link">${author}</a>`
          : author,
      )
      .join(", ")}`;
  };
</script>

<div class="container">
  <header>
    <h1>Hobbs Energy-Environment Decisions Group</h1>
    <p class="explanation">
      We use optimization, economics, and decision analysis to plan, operate,
      and analyze power systems and their environmental effects, and for
      ecosystem restoration. In this website, you can learn about the research
      questions we are interested in and the methods we use, be introduced to
      our students and graduates, and learn about Hopkins' graduate programs in
      environmental and energy systems & policy.
    </p>
    <p class="explanation">
      This page contains explanations of our papers, with interactive
      visualizations. See the <a
        href="https://hobbsgroup.johnshopkins.edu/home.html">main site</a
      > for more information about the Hobbs Energy-Environment Decisions Group.
    </p>
  </header>

  <div class="grid">
    {#each data.sites as site}
      <div class="card">
        <a href="/paper/{site.paper}" class="paper-title">
          {site.title}
        </a>
        <div class="date">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="16" y1="2" x2="16" y2="6"></line>
            <line x1="8" y1="2" x2="8" y2="6"></line>
            <line x1="3" y1="10" x2="21" y2="10"></line>
          </svg>
          {site.publication_date}
        </div>
        <div>
          {@html formatAuthors(site.authors)}
        </div>
        <div style="font-size: 0.8rem">
          Paper: <a href="https://scholar.google.com/scholar?q={site.pdf_title}"
            >{site.pdf_title}</a
          >
        </div>
      </div>
    {/each}
  </div>
</div>

<div>
  <p class="footer">
    Code for this site is on
    <a
      href="https://github.com/paulhobbs/benhobbs-papers"
      target="_blank"
      class="footer"
      rel="noopener">GitHub</a
    >.
  </p>
</div>

<style>
  :global(body) {
    font-family:
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      Roboto,
      Oxygen,
      Ubuntu,
      Cantarell,
      "Open Sans",
      "Helvetica Neue",
      sans-serif;
    background-color: #f8f9fa; /* Light grey background */
    color: #343a40; /* Darker base text color */
    margin: 0; /* Ensure no default body margin */
    padding: 0; /* Ensure no default body padding */
    background-image: url("/Mountain_Grid.jpg");
    background-size: cover;
    background-repeat: no-repeat;
    background-attachment: fixed;
  }
  
  .footer {
    text-align: center;
    margin: 0 auto;
    color: rgb(255,255,255, 0.9);
  }

  .container {
    max-width: 1140px; /* Slightly narrower */
    margin: 0 auto;
    padding: 3rem 1rem; /* More vertical padding */
  }

  header {
    text-align: center;
    padding-top: 0.15rem;
    padding-bottom: 0.15rem; /* More space below header */
    margin-bottom: 3rem;
    border-radius: 12px;
    background-color: rgba(250,250,250,0.9);
  }

  h1 {
    font-size: 3rem; /* Slightly larger */
    font-weight: 700; /* Bolder */
    color: #212529; /* Slightly darker */
    margin-bottom: 1rem;
  }

  .subtitle {
    font-size: 1.2rem;
    color: #6c757d; /* Softer grey */
    margin-bottom: 1.5rem;
  }

  .explanation {
    max-width: 700px; /* Limit width for readability */
    margin: 0 auto 2rem auto; /* Center and add bottom margin */
    color: #232629; /* Slightly darker than subtitle */
    line-height: 1.6;
    font-size: 1rem;
    text-align: justify;
  }

  .grid {
    display: grid;
    gap: 2rem; /* More gap */
    grid-template-columns: repeat(
      auto-fill,
      minmax(320px, 1fr)
    ); /* Slightly larger min width */
  }

  .card {
    background: #ffffff; /* Explicit white */
    border-radius: 12px; /* Softer corners */
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05); /* Softer shadow */
    padding: 2rem; /* More padding */
    transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
    display: flex; /* Use flexbox for layout */
    flex-direction: column; /* Stack elements vertically */
    /* Removed justify-content: space-between; to let content flow naturally */
  }

  .card:hover {
    transform: translateY(-4px);
    box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1); /* Slightly stronger hover shadow */
  }

  .paper-title {
    font-size: 1.2rem; /* Larger title */
    font-weight: 600; /* Bolder title */
    color: #0056b3; /* Darker blue */
    text-decoration: none;
    display: block;
    margin-bottom: 0.75rem; /* Reduced margin */
    line-height: 1.4;
  }

  .paper-title:hover {
    text-decoration: underline;
  }

  .date {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #6c757d; /* Softer grey */
    font-size: 0.85rem; /* Slightly smaller */
    margin-bottom: 0.75rem; /* Space below date */
  }

  .date svg {
    flex-shrink: 0;
    color: #6c757d; /* Match text color */
    position: relative;
    top: -1px; /* Minor alignment tweak */
  }

  /* Style the author section directly */
  .card > div:last-child {
    /* Target the div containing authors */
    margin-top: auto; /* Push authors to the bottom if using flex space-between */
    padding-top: 1rem; /* Add space above authors if content is short */
    font-size: 0.9rem;
    color: #495057; /* Consistent text color */
    line-height: 1.5;
  }
</style>
