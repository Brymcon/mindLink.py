# Obsidian Gemini Tagging & Linking Agent

This Python script is a powerful agent designed to automatically organize your Obsidian vault. It leverages the power of Google's Gemini 2.5 Flash model to analyze your notes, generate context-aware tags, and create links between related notes, turning your vault into a dynamic, interconnected knowledge graph.

## Features

- **Automated Tagging**: Analyzes the content of your notes and suggests relevant tags, including both topic tags (e.g., `#python`, `#AI`) and type tags (e.g., `#article`, `#project`).
- **Context-Aware Suggestions**: Uses not only the note's content but also data from related notes to provide highly relevant and consistent tags.
- **Key Concept Extraction**: Identifies and extracts key concepts from your notes to provide better context for tag generation.
- **Related Notes Linking**: Automatically creates a "Related Notes" section in each note, linking to other relevant notes based on shared tags.
- **Flexible Configuration**: A simple `config.yaml` file allows you to customize the script's behavior, including your vault path, API keys, and model settings.
- **Dry Run Mode**: Run the script in a "read-only" mode to see what changes it would make without modifying any of your files.

## Prerequisites

- Python 3.7+
- An Obsidian vault
- A Google AI API key

## Setup

1.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **Install Dependencies**:
    ```bash
    pip install pyyaml google-generativeai
    ```

3.  **Configure the Script**:
    - Rename `config.example.yaml` to `config.yaml`.
    - Open `config.yaml` and set the following:
        - `obsidian_vault_path`: The full path to your Obsidian vault.
        - `dry_run`: Set to `true` for the first run to ensure everything is working as expected.
        - `gemini.api_key`: Your Google AI API key. For better security, you can set this as an environment variable and reference it as `!env GOOGLE_API_KEY`.

## Running the Script

Once you've completed the setup, you can run the script from your terminal:

```bash
python obsidianTag.py
```

The script will perform the following steps:
1.  **Analyze Vault**: Read all of your notes and parse their content and frontmatter.
2.  **Compute Relationships**: Identify relationships between notes based on shared tags.
3.  **Generate Tags & Links**: For each note, it will:
    - Extract key concepts.
    - Generate suggested tags using the Gemini model.
    - Create a list of related notes.
4.  **Update Notes**: If `dry_run` is `false`, it will update your notes with the new tags and related notes section.

## How It Works

The script is divided into several key components:
- **Configuration Loading**: Securely loads your settings, including your API key.
- **Vault Analysis**: Scans your vault to build a comprehensive understanding of your notes.
- **Relationship Mapping**: Creates a map of how your notes are connected.
- **LLM Interaction**: Communicates with the Gemini API to get intelligent tag suggestions.
- **Note Modification**: Carefully updates your notes while preserving their original content.

This agent is designed to be a smart, automated assistant for your knowledge management, helping you to uncover hidden connections and build a more powerful personal knowledge base.

## License

MIT

## Acknowledgements

- Google's Gemini API for the AI capabilities
- The Obsidian community for inspiration 
