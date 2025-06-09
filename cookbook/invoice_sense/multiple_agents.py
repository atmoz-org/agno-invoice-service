from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.memory.v2 import Memory

# Shared memory for consistency across models
shared_memory = Memory()

# Create agents with different models but shared memory
agents = {
    "openai": Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        memory=shared_memory,
        add_history_to_messages=True,
    ),
    "claude": Agent(
        model=Claude(id="claude-3-5-sonnet-20241022"),
        memory=shared_memory,
        add_history_to_messages=True,
    )
}

# Function to get the right agent based on user selection
def get_agent(model_choice):
    return agents.get(model_choice, agents["openai"])  # Default to OpenAI

# Usage example
user_model_choice = "claude"
selected_agent = get_agent(user_model_choice)
selected_agent.print_response("Hello, how are you?", user_id="user_123")