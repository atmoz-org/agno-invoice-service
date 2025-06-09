from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
from agno.models.openai import OpenAIChat
import pdfplumber
import os

# This function will allow the agent to access specialized terms
def domain_specific_jargon():
    return {
        "invoice": ["Invoice No", "Invoice Date", "Billing Amount", "Tax", "Due Date"],
        "accounting": ["Debit", "Credit", "Balance Sheet", "Liabilities", "Assets"]
    }

# Initialize a SQLite storage for agent sessions
storage = SqliteStorage(
    table_name="agent_sessions",
    db_file="tmp/agent_memory.db"
)

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pdfplumber"""
    extracted_text = ""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} was not found.")
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            extracted_text += page.extract_text() or ""
    return extracted_text

def process_invoice(file_path: str):
    # Extract text from the PDF
    pdf_text = extract_text_from_pdf(file_path)

    # Example of integrating specific knowledge terms
    specialized_terms = domain_specific_jargon()

    # Initialize the agent with the required tools
    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        storage=storage,
        description="Agent processes invoices by incorporating domain-specific knowledge.",
        markdown=True
    )

    # Include additional knowledge in the prompt
    prompt = f"""
    Extract invoice details such as invoice number, date, and total from the following text:

    {pdf_text}

    Use these guidelines for parsing:
    - Recognize terms like {specialized_terms['invoice']}.
    - Apply accounting knowledge such as {specialized_terms['accounting']}.
    """

    # Run the agent
    response = agent.run(prompt)

    # Display the processing result
    print(response)

# Provide the absolute path to your local PDF file
process_invoice("test.pdf")