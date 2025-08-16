import os
import json
from poml.api import poml  # Assuming the poml library is available

# Directory containing POML files
POML_DIR = os.path.join(os.path.dirname(__file__), 'prompts')
# Directory to save pre-processed JSON files
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'processed_prompts')

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def preprocess_poml_to_json():
    """
    Convert POML files to JSON and save them.
    """
    for filename in os.listdir(POML_DIR):
        if filename.endswith('.poml'):
            poml_path = os.path.join(POML_DIR, filename)
            try:
                # Process the POML file into a dictionary format
                processed_prompt = poml(poml_path, format="dict")

                # Save as JSON
                json_filename = f"{os.path.splitext(filename)[0]}.json"
                json_path = os.path.join(OUTPUT_DIR, json_filename)
                with open(json_path, 'w') as json_file:
                    json.dump(processed_prompt, json_file, indent=4)

                print(f"Processed {filename} -> {json_filename}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    preprocess_poml_to_json()
