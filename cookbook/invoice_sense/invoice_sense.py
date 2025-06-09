from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
from agno.models.openai import OpenAIChat
import pdfplumber
import os

# Initialize SQLite storage for the agent session
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

    # Initialize the agent with the required tools
    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        storage=storage, # Use local storage
        description="Agent processes invoices to extract details directly from text.",
        markdown=True
    )

    # Run the agent to interpret the text from the PDF
    response = agent.run(
        f"Extract invoice details such as invoice number, date, and total from the following text:\n\{pdf_text}"
    )

    # Output the response from the model
    print(response)

# Use the absolute path to the PDF file
process_invoice("test.pdf")