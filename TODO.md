## Homepage

- [x] Add an explanation of what this website is about
  - [x] Add a link to github repo with source code for the scripts which generated the site
- [x] Add a link to your jhu.edu site

For each card:
- [x] Add citation with full names & link to article
- [x] Add publish date
- [ ] Regenerate metadata

## Subpage

- [ ] Add citation with full names & link to article
- [ ] Add publish date

## Improved generated sites

- [ ] Fix **markdown** formatting in HTML. Maybe remove it from the prompt, instead using <strong>emphasis</strong> with HTML tags to prime the model to stop generating it in the first place?
  - [ ] Alternatively, do a pass-over with gemini to specifically fix markdown issues.
- [ ] Generate a screenshot and add to the context for revisions.
  - [ ] [Use a browser MCP for this?](https://www.reddit.com/r/ClaudeAI/comments/1k0f3vs/musthave_mcp_servers_for_coding_and_beyond/)
  - [ ] Would need an agent library to use MCPs. Maybe [fast-agent](https://fast-agent.ai/mcp/)?


## Get more papers

- [x] Create a Python script (`agents/download_pdfs.py`) to download all PDF links from `https://hobbsgroup.johnshopkins.edu/publications.html`.
- [x] Validate the created script.