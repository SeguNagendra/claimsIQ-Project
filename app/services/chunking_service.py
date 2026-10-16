class ChunkingService:
    def __init__(self, chunk_size=1200, chunk_overlap=200):
        if chunk_size < 1 or chunk_overlap < 0 or chunk_overlap >= chunk_size: raise ValueError("Require chunk_size > chunk_overlap >= 0")
        self.chunk_size, self.chunk_overlap = chunk_size, chunk_overlap
    def chunk_pages(self, pages):
        chunks=[]; number=0
        for page in pages:
            text=" ".join(page["text"].split()); start=0
            while start < len(text):
                end=min(start+self.chunk_size,len(text)); part=text[start:end].strip()
                if part: chunks.append({"chunk_number":number,"page_number":page.get("page_number"),"chunk_text":part}); number+=1
                if end >= len(text): break
                start=end-self.chunk_overlap
        return chunks
