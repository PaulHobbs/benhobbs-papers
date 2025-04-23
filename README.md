# Research Paper Explorer

This project provides a system for automatically generating interactive web pages that explain the core ideas of academic papers. Inspired by the explanatory styles of Bret Victor and Bartosz Ciechanowski, the goal is to make complex research concepts accessible and intuitive through interactive visualizations and simulations.

## Features

- **Automated Generation:** A Python script processes academic paper PDFs and uses the Gemini language model to generate single, self-contained HTML files.
- **Interactive Explanations:** Generated HTML pages incorporate interactive JavaScript visualizations (using libraries like D3.js and p5.js), mathematical rendering (MathJax), and responsive styling (Bootstrap) to build intuition for the paper's concepts.
- **Browsable Interface:** A Svelte-based frontend application provides a user-friendly interface to browse and access the generated paper explanations.
- **Link Correction:** The generation process includes a step to automatically correct broken Wikipedia links using a language model with search capabilities.

## How it Works

1.  **Paper Processing:** The `agents/create_site.py` script takes one or more PDF file paths as command-line arguments.
2.  **HTML Generation:** The script sends the PDF content and a detailed prompt to the Gemini language model. The prompt guides the model to produce an interactive HTML explanation focusing on key concepts, models, and findings, prioritizing interactive elements over static content.
3.  **Link Fixing:** The generated HTML is then passed to another language model instance equipped with a Google Search tool to find and correct any incorrect Wikipedia links and ensure proper HTML formatting.
4.  **File Saving:** The final HTML is saved to the `static/sites/` directory.
5.  **Index Update:** Metadata about the generated site (title, authors, path, etc.) is added to `src/lib/sites.json`, which serves as an index for the frontend application.
6.  **Frontend Display:** The Svelte application (`src/routes/+page.svelte`) reads the `sites.json` file and displays the available paper explanations as a grid of cards, linking to the generated HTML files.

## Technologies Used

- **Python:** For the backend generation script.
- **Google Gemini API:** Language models for content generation and link correction.
- **Svelte:** For the frontend browsing application.
- **HTML, CSS, JavaScript:** The core technologies for the generated interactive pages.
- **D3.js, p5.js:** JavaScript libraries used within the generated HTML for visualizations and simulations.
- **MathJax:** For rendering mathematical notation in the generated HTML.
- **Bootstrap:** For styling and layout in the generated HTML.

## Setup and Usage

To set up and run the project locally:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/paulhobbs/benhobbs-papers.git
    cd benhobbs-papers
    ```
2.  **Set up Python environment:**
    Install Python dependencies. It's recommended to use a virtual environment.
    ```bash
    uv venv .venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    ```
3.  **Set up Node.js environment:**
    Install Node.js dependencies using pnpm (or npm/yarn).
    ```bash
    pnpm install
    ```
4.  **Configure Gemini API:**
    Obtain a Google Gemini API key from aistudio.google.com, and set it as an
    environment variable (`GOOGLE_API_KEY`).
    ```bash
    export GOOGLE_API_KEY='YOUR_API_KEY'
    ```
5.  **Generate a paper explanation:**
    Run the Python script, providing the path to a PDF file.
    ```bash
    agents/create_site.py
    ```
    This will generate an HTML file in `static/sites/` and update the manifest `src/lib/sites.json`.
6.  **Run the frontend application:**
    Start the Svelte development server.
    ```bash
    pnpm run dev
    ```
    The application should be available at `http://localhost:5173` (or a similar address). You can browse the generated paper explanations there.

## Inspiration

The interactive and explanatory style of the generated content is heavily inspired by the work of:

-   **Bret Victor:** Known for his dynamic explanations and interactive tools for understanding complex systems.
-   **Bartosz Ciechanowski:** Renowned for creating incredibly detailed and interactive web pages that explain scientific and technical concepts with stunning visualizations.