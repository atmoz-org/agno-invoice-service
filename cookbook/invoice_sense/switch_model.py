from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.memory.v2 import Memory

# Create agent with initial model
agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    memory=Memory(),
    add_history_to_messages=True,
)

# Hardcoded lists of available models for each provider (update as needed)
OPENAI_MODELS = [
    "gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4"
]
CLAUDE_MODELS = [
    "claude-3-5-sonnet-20241022", "claude-sonnet-4-20250514"
]

# Functions to access the available model lists
def get_openai_models():
    """Return the list of OpenAI model IDs available for selection."""
    return OPENAI_MODELS

def get_claude_models():
    """Return the list of Anthropic Claude model IDs available for selection."""
    return CLAUDE_MODELS

# Function to switch the agent's model based on provider and model_choice
def switch_model(provider: str, model_choice: str):
    """
    Configure the global agent to use the given provider and model ID.
    provider should be 'OpenAI' or 'Anthropic'; model_choice is the specific model identifier.
    """
    if provider.lower() == "openai":
        agent.model = OpenAIChat(id=model_choice)
    elif provider.lower() == "anthropic":
        agent.model = Claude(id=model_choice)
    else:
        raise ValueError(f"Unknown provider: {provider}")


