from io import BytesIO

class TextExtractionService:
    def extract_pdf(self, content):
        import fitz
        pdf = fitz.open(stream=content, filetype="pdf")
        try:
            return [{"page_number": i + 1, "text": page.get_text("text").strip()} for i, page in enumerate(pdf) if page.get_text("text").strip()]
        finally:
            pdf.close()

    def extract_docx(self, content):
        from docx import Document as WordDocument
        document = WordDocument(BytesIO(content))
        text = "\\n".join(p.text.strip() for p in document.paragraphs if p.text.strip())
        return [{"page_number": None, "text": text}] if text else []

    def extract(self, content, file_type):
        if file_type == ".pdf": return self.extract_pdf(content)
        if file_type == ".docx": return self.extract_docx(content)
        raise ValueError(f"Unsupported file type: {file_type}")
