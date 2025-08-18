import os
import json
from services.poml_service import POMLService  # Correctly import the service

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
    poml_service = POMLService(prompts_directory='prompts')
    
    for filename in os.listdir(POML_DIR):
        if filename.endswith('.poml'):
            template_name = os.path.splitext(filename)[0]
            try:
                # Load the template content using the POMLService
                template_content = poml_service.load_template(template_name)
                
                # Create a dictionary to store the processed prompt
                processed_prompt = {
                    "template_name": template_name,
                    "content": template_content
                }

                # Save as JSON
                json_filename = f"{template_name}.json"
                json_path = os.path.join(OUTPUT_DIR, json_filename)
                with open(json_path, 'w') as json_file:
                    json.dump(processed_prompt, json_file, indent=4)

                print(f"Processed {filename} -> {json_filename}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    preprocess_poml_to_json()
