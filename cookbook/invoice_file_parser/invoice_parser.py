import os
from pathlib import Path
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from agno.knowledge.pdf import PDFReader

def extract_text_from_pdf(pdf_path: str) -> str:
    # Create a PDFReader instance
    reader = PDFReader()
    # Load the content from a PDF file
    document = reader.load_document(pdf_path)
    # Extract text from the PDFDocument
    return document.extract_text()

def extract_text_from_image(image_path: str) -> str:
    image = Image.open(image_path)
    return pytesseract.image_to_string(image)

def process_files_in_folder(input_folder: str, output_folder: str):
    supported_extensions = ['.pdf', '.jpeg', '.jpg', '.png']

    for file_name in os.listdir(input_folder):
        file_path = Path(input_folder) / file_name

        if file_path.suffix.lower() in supported_extensions:
            # Extract data based on file type
            if file_path.suffix.lower() == '.pdf':
                extracted_data = extract_text_from_pdf(file_path)
            else:
                extracted_data = extract_text_from_image(file_path)

            # Save to output folder
            output_file_path = Path(output_folder) / f"{file_path.stem}.txt"
            with open(output_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(extracted_data)

if __name__ == "__main__":
    input_directory = './test_data'
    output_directory = './output'
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    process_files_in_folder(input_directory, output_directory)