import json
import os
import pdfplumber
from datetime import datetime
from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
from agno.models.openai import OpenAIChat

# Initialize SQLite storage for agent sessions
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

def save_to_json(data: dict, base_name: str) -> None:
    """Save extracted data to a JSON file with a timestamped filename"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{timestamp}.json"
    with open(filename, "w") as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Data saved to {filename}")

def parse_response(response_content: str) -> dict:
    """Parse the response content to extract invoice details, cleaning up formatting"""
    details = {}
    try:
        lines = response_content.split('\n')
        for line in lines:
            if "Invoice Number" in line:
                invoice_number = line.split(':')[-1].strip()
                details['invoice_number'] = invoice_number.replace('**', '').strip()
            elif "Invoice Date" in line:
                date = line.split(':')[-1].strip()
                details['date'] = date.replace('**', '').strip()
            elif "Total Amount" in line:
                total_amount = line.split(':')[-1].strip()
                # Clean and normalize the total amount
                total_amount = total_amount.replace('**', '').replace(',', '').strip()
                details['total'] = total_amount
    except Exception as e:
        print(f"Error parsing response content: {e}")
    return details



def process_invoice(file_path: str):
    # Extract text from the PDF
    pdf_text = extract_text_from_pdf(file_path)

    # Initialize the agent with the required tools
    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        storage=storage,
        description="Agent processes invoices to extract details directly from text.",
        markdown=True
    )

    # Run the agent to interpret the text from the PDF
    response = agent.run(
        f"Extract invoice details such as invoice number, date, and total from the following text:\n\{pdf_text}"
    )

    # Assume the response object has a content attribute with the text result
    extracted_text = response.content if hasattr(response, 'content') else str(response)

    # Use a custom function to parse and extract relevant information from response content
    extracted_data = parse_response(extracted_text)

    # Save extracted data to JSON file
    save_to_json(extracted_data, os.path.splitext(os.path.basename(file_path))[0])

# Provide the absolute path to your local PDF file
process_invoice("test.pdf")