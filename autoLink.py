import os
import glob
import yaml
import collections
from pathlib import Path
import google.generativeai as genai
from typing import List, Dict, Any, Set, Tuple

# --- Configuration Loading ---

def load_config(config_path='config.yaml'):
    """Loads the configuration from a YAML file."""
    try:
        with open(config_path, 'r') as f:
            # Use a custom loader to handle '!env' tags for environment variables
            loader = yaml.SafeLoader
            loader.add_constructor('!env', lambda _, node: os.environ.get(node.value, ''))
            config = yaml.load(f, Loader=loader)
        
        # Configure the Google AI client
        api_key = config.get('gemini', {}).get('api_key')
        if not api_key:
            raise ValueError("Gemini API key not found in config.yaml or environment variables.")
        genai.configure(api_key=api_key)
        
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        print("Please create a 'config.yaml' file based on the example.")
        return None
    except (yaml.YAMLError, ValueError) as e:
        print(f"Error processing configuration: {e}")
        return None

# --- Note and Vault Analysis ---

def analyze_vault(vault_path):
    """
    Reads all notes in the vault and extracts their content and frontmatter.
    Returns a list of dictionaries, each representing a note.
    """
    notes = []
    skipped_files = 0
    # Using pathlib for better cross-platform path handling
    for file_path in Path(vault_path).rglob('*.md'):
        try:
            # Skip non-text files or files that can't be read as text
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                print(f"  - Skipping binary or non-text file: {file_path.name}")
                skipped_files += 1
                continue

            # Simple frontmatter parsing
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                note_content = parts[2]
                try:
                    frontmatter = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError:
                    frontmatter = {} # Ignore malformed YAML
            else:
                note_content = content
                frontmatter = {}

            notes.append({
                "path": file_path,
                "name": file_path.stem,
                "content": note_content,
                "frontmatter": frontmatter
            })
        except Exception as e:
            print(f"  - Warning: Could not read or parse {file_path.name}. Error: {e}")
            skipped_files += 1
    
    print(f"  - Found {len(notes)} valid notes in the vault. Skipped {skipped_files} files.")
    
    # Validate notes structure
    for i, note in enumerate(notes[:5]):  # Check first 5 notes for debugging
        if not isinstance(note, dict):
            print(f"  - Warning: Note at index {i} is not a dictionary: {type(note)}")
        else:
            print(f"  - Debug: Note at index {i} has keys: {note.keys()}")
    
    return notes

def compute_related_notes(notes, config):
    """Computes related notes based on shared tags."""
    threshold = config.get('linking', {}).get('shared_tags_threshold', 2)
    limit = config.get('linking', {}).get('related_notes_limit', 5)
    
    # Debug information
    print(f"  - Computing related notes with threshold {threshold} and limit {limit}")
    print(f"  - Notes list type: {type(notes)}, length: {len(notes)}")
    
    # Ensure all items in notes are dictionaries and have the required structure
    valid_notes = []
    for i, note in enumerate(notes):
        # Skip any non-dictionary notes
        if not isinstance(note, dict):
            print(f"  - Warning: Skipping note at index {i}, not a dictionary: {type(note)}")
            continue
            
        # Skip notes without required fields
        if 'frontmatter' not in note or 'path' not in note:
            print(f"  - Warning: Skipping note at index {i}, missing required fields")
            continue
            
        valid_notes.append(note)
    
    print(f"  - After validation, {len(valid_notes)} valid notes remain.")
    
    # EXTRA DEBUGGING: Verify all valid_notes are dictionaries
    for i, note in enumerate(valid_notes):
        if not isinstance(note, dict):
            print(f"  - CRITICAL: Found non-dictionary in valid_notes at index {i}: {type(note)}")
            print(f"  - Value: {str(note)[:100]}")
            # Replace with a placeholder to avoid crashing
            valid_notes[i] = {"path": Path("invalid.md"), "name": "invalid", "content": "", "frontmatter": {}}
    
    tag_to_notes = collections.defaultdict(set)
    for i, note in enumerate(valid_notes):
        try:
            # Safety check - this should never happen due to validation above
            if not isinstance(note, dict):
                print(f"  - Error: Note at index {i} in valid_notes is not a dictionary: {type(note)}")
                continue
                
            # Ensure 'tags' exists and is a list before processing
            tags = note.get('frontmatter', {}).get('tags', [])
            if isinstance(tags, list):
                for tag in tags:
                    # Ensure each tag is a string before adding it to the map
                    if isinstance(tag, str):
                        tag_to_notes[tag].add(note['path'])
        except Exception as e:
            print(f"  - Error in tag processing for note {i}: {e}")
            # Continue with the next note

    related_notes_map = {}
    for i, note in enumerate(valid_notes):
        try:
            # Safety check - this should never happen due to validation above
            if not isinstance(note, dict):
                print(f"  - Error: Note at index {i} in valid_notes is not a dictionary")
                continue
                
            path = note['path']
            tags = note.get('frontmatter', {}).get('tags', [])
            
            # Skip if tags are missing or not a list
            if not isinstance(tags, list):
                continue

            counter = collections.Counter()
            for tag in tags:
                # Final safeguard: only process tags that are strings
                if isinstance(tag, str) and tag in tag_to_notes:
                    counter.update(tag_to_notes[tag])
            
            counter.pop(path, None)  # Exclude self

            # Sort related notes by the number of shared tags
            related = sorted(
                [(related_path, count) for related_path, count in counter.items() if count >= threshold],
                key=lambda x: x[1],
                reverse=True
            )
            related_notes_map[path] = [related_path for related_path, _ in related][:limit]
        except Exception as e:
            print(f"\n--- ERROR in compute_related_notes ---")
            print(f"Error processing note at index {i}")
            print(f"Error: {e}")
            print(f"------------------------------------------\n")
            # Continue processing other notes instead of crashing
            continue

    print(f"  - Computed relationships between notes.")
    return related_notes_map

# --- LLM Interaction ---

def extract_key_concepts(note_content: str, config: Dict[str, Any]) -> List[str]:
    """
    Extract key concepts from the note content using Gemini.
    This helps provide better context for tag generation.
    """
    model_name = config.get('gemini', {}).get('model', 'gemini-2.5-flash-preview-05-20')
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
    Read the following note and extract 5-7 key concepts or topics that are central to the content.
    Just list the concepts separated by commas, without any explanation.
    
    Note Content:
    {note_content[:8000]}  # Limit content length to avoid token limits
    """
    
    try:
        # Configure generation parameters
        generation_config = {"temperature": 0.2}
            
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # Clean up response to handle potential markdown or other formatting
        cleaned_text = response.text.replace('*', '').strip()
        concepts = [concept.strip() for concept in cleaned_text.split(",")]
        return [concept for concept in concepts if concept]  # Filter out empty concepts
    except Exception as e:
        print(f"  - Error extracting key concepts: {e}")
        return []

def get_refined_tags(note_content, related_notes_data, key_concepts, config):
    """
    Suggests tags for a note using Gemini, providing related notes for context.
    Enhanced with key concepts and more detailed context.
    """
    model_name = config.get('gemini', {}).get('model', 'gemini-2.5-flash-preview-05-20')
    model = genai.GenerativeModel(model_name)

    # Format related notes with their tags for better context
    related_notes_context = []
    for note_data in related_notes_data:
        name = note_data.get("name", "")
        tags = note_data.get("tags", [])
        tags_str = ", ".join(tags) if tags else "no tags"
        related_notes_context.append(f"- {name} (tags: {tags_str})")
    
    related_notes_str = "\n".join(related_notes_context)
    key_concepts_str = ", ".join(key_concepts) if key_concepts else "No key concepts identified"
    
    prompt = f"""
    You are an expert in knowledge management and personal knowledge graphs.
    Your task is to analyze the following note and generate a list of 5-10 highly relevant tags.
    
    Consider:
    1. The note's content and main topics
    2. The key concepts identified: {key_concepts_str}
    3. Related notes and their existing tags (for consistency)
    4. Create a balanced mix of specific and general tags
    
    Generate tags that will:
    - Create meaningful connections between notes
    - Help with future discoverability
    - Maintain consistency with existing tags where appropriate
    - Include both topic tags and type tags (e.g., #article, #project, #reference)
    
    Output ONLY the tags, separated by commas, without any explanation or additional text.
    
    ---
    Related Notes:
    {related_notes_str}
    ---
    Note Content (excerpt):
    {note_content[:8000]}  # Limit content length to avoid token limits
    ---
    Tags:
    """
    
    try:
        # Configure generation parameters
        generation_config = {"temperature": 0.2}
            
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # Clean up response to handle potential markdown or other formatting
        cleaned_text = response.text.replace('*', '').strip()
        tags = [tag.strip() for tag in cleaned_text.split(",")]
        return [tag for tag in tags if tag]  # Filter out empty tags
    except Exception as e:
        print(f"  - Error suggesting tags: {e}")
        return []

# --- Note Modification ---

def update_note_file(note_path, new_tags, related_note_paths, config):
    """
    Updates a note file with new tags in the frontmatter and a 'Related Notes' section in the body.
    """
    if config.get('dry_run', True):
        print("  - Dry run: No changes will be written to the file.")
        return

    try:
        # Read the entire file to preserve it
        with open(note_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
        
        parts = full_content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str, body_content = parts[1], parts[2]
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        else:
            body_content = full_content
            frontmatter = {}
            
        # Update tags
        frontmatter['tags'] = new_tags

        # Prepare the related notes markdown section
        related_notes_md = "## Related Notes\n" + "\n".join(
            [f"- [[{path.stem}]]" for path in related_note_paths]
        )
        start_marker = "<!-- related notes start -->"
        end_marker = "<!-- related notes end -->"

        # Replace or append the related notes section
        if start_marker in body_content:
            before, _, after = body_content.partition(start_marker)
            _, _, after = after.partition(end_marker)
            body_content = before.rstrip() + f"\n\n{start_marker}\n{related_notes_md}\n{end_marker}\n" + after.lstrip()
        else:
            body_content = body_content.rstrip() + f"\n\n{start_marker}\n{related_notes_md}\n{end_marker}\n"
        
        # Reconstruct and write the file
        updated_frontmatter = yaml.dump(frontmatter, default_flow_style=False).strip()
        updated_content = f"---\n{updated_frontmatter}\n---\n{body_content.lstrip()}"
        
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print("  - Note updated successfully.")

    except Exception as e:
        print(f"  - Error updating note {note_path.name}: {e}")


# --- Main Execution ---

def main():
    """Main function to run the tagging and linking process."""
    config = load_config()
    if not config:
        return

    # Fix Windows paths by using forward slashes
    vault_path_str = config['obsidian_vault_path'].replace('\\', '/')
    vault_path = Path(vault_path_str)
    
    if not vault_path.is_dir():
        print(f"Error: Vault path '{vault_path}' not found or is not a directory.")
        return

    print(f"Starting analysis of vault: {vault_path}")
    if config.get('dry_run', True):
        print("--- DRY RUN MODE ENABLED ---")

    print("\n--- Phase 1: Analyzing vault and computing relationships ---")
    notes_data = analyze_vault(vault_path)
    if not notes_data:
        print("No notes found in vault.")
        return
    
    # Ensure notes_data is a list of dictionaries
    if not isinstance(notes_data, list):
        print(f"Error: Expected notes_data to be a list, got {type(notes_data)}")
        return
    
    # Filter out any non-dictionary items in notes_data
    valid_notes = []
    invalid_count = 0
    for i, note in enumerate(notes_data):
        if isinstance(note, dict) and 'path' in note and 'frontmatter' in note:
            valid_notes.append(note)
        else:
            invalid_count += 1
            if invalid_count <= 5:  # Only show first 5 invalid notes to avoid flooding console
                print(f"  - Warning: Skipping note at index {i} because it's not a valid note dictionary: {type(note)}")
                if isinstance(note, str):
                    print(f"    - String value (first 50 chars): {note[:50]}")
    
    if invalid_count > 5:
        print(f"  - Warning: {invalid_count - 5} more invalid notes were found but not shown")
    
    print(f"  - After filtering, {len(valid_notes)} valid notes remain. {invalid_count} notes were skipped.")
    
    # Final validation to ensure all notes are dictionaries
    for i in range(len(valid_notes)):
        if not isinstance(valid_notes[i], dict):
            print(f"  - Critical: Replacing invalid note at index {i} with placeholder")
            valid_notes[i] = {"path": Path("invalid_note.md"), "name": "invalid_note", "content": "", "frontmatter": {}}
    
    try:
        related_notes_map = compute_related_notes(valid_notes, config)
        print(f"Analysis complete. Found {len(valid_notes)} valid notes.")
    except Exception as e:
        print(f"Error during relationship computation: {e}")
        print("Continuing with an empty relationship map")
        related_notes_map = {}

    print("\n--- Phase 2: Generating context-aware tags and updating notes ---")
    # Process all notes instead of a small test set
    print(f"  - Processing all {len(valid_notes)} notes...")
    
    for i, note in enumerate(valid_notes):
        try:
            path = note['path']
            print(f"\nProcessing: {note['name']} ({i+1}/{len(valid_notes)})")
            
            # Get related notes for context
            related_paths = related_notes_map.get(path, [])
            related_notes_data = []
            
            # Collect more detailed information about related notes for better context
            for related_path in related_paths:
                for n in valid_notes:
                    if n['path'] == related_path:
                        related_notes_data.append({
                            "name": n['name'],
                            "tags": n.get('frontmatter', {}).get('tags', [])
                        })
                        break
            
            # Extract key concepts from the note content
            key_concepts = extract_key_concepts(note['content'], config)
            print(f"  - Key concepts identified: {key_concepts}")
            
            # Get refined tags from Gemini
            suggested_tags = get_refined_tags(note['content'], related_notes_data, key_concepts, config)
            
            existing_tags = note.get('frontmatter', {}).get('tags', [])
            if not isinstance(existing_tags, list):
                existing_tags = []
                
            # Combine and deduplicate tags
            final_tags = sorted(list(set(existing_tags + suggested_tags)))
            
            print(f"  - Existing tags: {existing_tags}")
            print(f"  - Suggested tags: {suggested_tags}")
            print(f"  - Final tags: {final_tags}")
            print(f"  - Related notes: {[data['name'] for data in related_notes_data]}")
            
            # Update the note file
            update_note_file(path, final_tags, related_paths, config)
        except Exception as e:
            print(f"Error processing note {i}: {e}")
            continue

    print("\nProcess complete.")

if __name__ == "__main__":
    main()

