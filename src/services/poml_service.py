import logging
from pathlib import Path
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

class POMLService:
    """Service for managing POML templates and rendering prompts."""
    
    def __init__(self, prompts_directory: str = "prompts"):
        """
        Initialize POML service.
        
        Args:
            prompts_directory: Directory containing .poml files
        """
        # Get the directory of the current file
        base_path = Path(__file__).parent.parent
        self.prompts_dir = base_path / prompts_directory
        self.templates_cache: Dict[str, str] = {}
        
        # Ensure prompts directory exists
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory {self.prompts_dir} does not exist")
        
        logger.info(f"POMLService initialized with prompts directory: {self.prompts_dir}")

    def load_template(self, template_name: str) -> str:
        """Load a POML template from file."""
        try:
            # Check cache first
            if template_name in self.templates_cache:
                return self.templates_cache[template_name]
            
            # Construct file path
            template_path = self.prompts_dir / f"{template_name}.poml"
            
            if not template_path.exists():
                raise FileNotFoundError(f"Template file not found: {template_path}")
            
            # Read template content
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Cache the template
            self.templates_cache[template_name] = template_content
            logger.info(f"Loaded POML template: {template_name}")
            
            return template_content
            
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {str(e)}")
            raise

    def render_template(self, template_content: str, context: Dict[str, Any]) -> str:
        """
        Render a POML template with context variables.
        
        This is a simplified POML renderer that extracts system instructions from XML format.
        """
        try:
            rendered = template_content
            
            # Simple variable substitution using {{variable}} syntax
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                rendered = rendered.replace(placeholder, str(value))
            
            # Extract system prompt from POML XML format
            # Look for <Paragraph speaker="system"> sections
            system_instructions = []
            
            # Split by lines and look for system paragraphs
            lines = rendered.split('\n')
            in_system_section = False
            current_section = None
            
            for line in lines:
                line = line.strip()
                
                # Check for section captions that might contain important context
                if line.startswith('<Section caption='):
                    caption = line.split('"')[1] if '"' in line else ""
                    if caption in ["Role Definition", "Behavioral Guidelines", "Workflow", "Tools"]:
                        current_section = caption
                        continue
                
                # Check for system paragraphs
                if '<Paragraph speaker="system">' in line:
                    in_system_section = True
                    continue
                elif '</Paragraph>' in line:
                    in_system_section = False
                    continue
                elif in_system_section and line:
                    # Clean up XML tags and add to system instructions
                    clean_line = line.replace('<', ' ').replace('>', ' ').strip()
                    if clean_line:
                        system_instructions.append(clean_line)
                
                # Also capture important workflow instructions
                elif current_section == "Workflow" and line and not line.startswith('<'):
                    clean_line = line.replace('<', ' ').replace('>', ' ').strip()
                    if clean_line and len(clean_line) > 10:  # Only meaningful lines
                        system_instructions.append(clean_line)
            
            # If we found system instructions, return them
            if system_instructions:
                # Add explicit tool usage instructions
                tool_instructions = """
IMPORTANT: You have access to several tools that you MUST use to help clients. When a client asks about their claim or wants to complete a claim form, you should:
1. First ask for their contact information (email or phone)
2. Use the get_claim_by_contact_info tool to look up their existing claims
3. Based on the result, either help them complete missing information or start a new claim
4. Use the appropriate tools (update_claim_data, transition_claim_type, etc.) as needed

Always use the available tools rather than just providing generic responses. Follow the workflow defined in your instructions.
"""
                return ' '.join(system_instructions) + tool_instructions
            else:
                # Fallback to entire rendered content if no System section found
                # But clean up XML tags
                cleaned = rendered.replace('<', ' ').replace('>', ' ').replace('&amp;', '&')
                return cleaned.strip()
                
        except Exception as e:
            logger.error(f"Error rendering template: {str(e)}")
            # Return fallback if rendering fails
            return "You are a helpful AI assistant for a law firm. Please assist the user professionally."

    def get_agent_instructions(self, agent_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Get rendered instructions for a specific agent."""
        try:
            if context is None:
                context = {}
            
            # Add default context variables
            default_context = {
                'user_message': context.get('user_message', ''),
                'user_id': context.get('user_id', ''),
                'timestamp': context.get('timestamp', ''),
            }
            
            # Merge contexts
            full_context = {**default_context, **context}
            
            # Load and render template
            template_content = self.load_template(agent_name)
            instructions = self.render_template(template_content, full_context)
            
            logger.debug(f"Rendered instructions for agent {agent_name}")
            return instructions
            
        except Exception as e:
            logger.error(f"Error getting instructions for agent {agent_name}: {str(e)}")
            # Return fallback instructions
            return self._get_fallback_instructions(agent_name)

    def _get_fallback_instructions(self, agent_name: str) -> str:
        """Provide fallback instructions if template loading fails."""
        fallback_instructions = {
            'initial_agent': '''You are the "Initial Intake Agent" for a personal injury law firm. 
Your primary goal is to collect initial lead data from new users, including their first name, 
last name, email, and phone number. Be polite, professional, and guide the user through the 
intake process. Do not answer legal questions or provide legal advice. If the user asks for 
legal advice, politely state that you are an intake agent and cannot provide legal advice, 
but you can connect them with a legal professional once you have their contact information.''',
            
            'portal_agent': '''You are the "Portal Agent" for a personal injury law firm's client portal. 
You assist existing, authenticated clients with their ongoing claims. You can help them check 
claim status, update claim information, and answer questions about their cases. You should be 
professional, empathetic, and helpful while maintaining client confidentiality and following 
legal guidelines.'''
        }
        
        return fallback_instructions.get(agent_name, 
            "You are a helpful AI assistant for a law firm. Please assist the user professionally.")

    def create_template_file(self, template_name: str, content: str) -> bool:
        """Create a new POML template file."""
        try:
            # Ensure prompts directory exists
            os.makedirs(self.prompts_dir, exist_ok=True)
            
            template_path = self.prompts_dir / f"{template_name}.poml"
            
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Clear cache for this template
            if template_name in self.templates_cache:
                del self.templates_cache[template_name]
            
            logger.info(f"Created POML template file: {template_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating template file {template_name}: {str(e)}")
            return False

    def list_templates(self) -> list:
        """List all available POML templates."""
        try:
            if not self.prompts_dir.exists():
                return []
            
            templates = []
            for file_path in self.prompts_dir.glob("*.poml"):
                templates.append(file_path.stem)  # filename without extension
            
            return sorted(templates)
            
        except Exception as e:
            logger.error(f"Error listing templates: {str(e)}")
            return []
