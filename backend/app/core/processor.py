
import os
from typing import Optional
from pathlib import Path
import logging
from pypdf import PdfReader
import docx

# Text normalization 
import re
import unicodedata

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextNormalizer:
    """Quick text normalizer embedded in processor"""
    
    def normalize(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Fix encoding
        text = unicodedata.normalize('NFKC', text)
        
        # Remove control characters (keep newlines)
        text = ''.join(c for c in text 
                      if unicodedata.category(c)[0] != 'C' or c in '\n\r\t')
        
        # Normalize whitespace
        text = re.sub(r' {2,}', ' ', text)  # Multiple spaces
        text = text.replace('\r\n', '\n').replace('\r', '\n')  # Line endings
        text = re.sub(r' +\n', '\n', text)  # Trailing spaces
        text = re.sub(r'\n{3,}', '\n\n', text)  # Excessive blank lines
        
        # Standardize quotes
        text = re.sub(r'[''‚]', "'", text)
        text = re.sub(r'[""„]', '"', text)
        
        return text.strip()


class ContractProcessor:
    """
    Main class for processing contract documents
    NOW WITH TEXT NORMALIZATION!
    """
    
    def __init__(self, normalize_text: bool = True):
        """
        Initialize the processor
        
        Args:
            normalize_text: Whether to normalize extracted text (recommended)
        """
        self.supported_formats = ['.pdf', '.docx', '.doc']
        self.normalize_text = normalize_text
        self.normalizer = TextNormalizer()
        
        logger.info("ContractProcessor initialized (with text normalization)")
    
    
    def extract_text(self, file_path: str, clean: bool = True) -> str:
        """
        Main method - extracts and optionally cleans text
        
        Args:
            file_path: Path to the contract file
            clean: Whether to normalize the text (default: True)
            
        Returns:
            Extracted (and optionally cleaned) text
        """
        # Validate file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_extension = Path(file_path).suffix.lower()
        
        if file_extension not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_extension}")
        
        logger.info(f"Processing file: {file_path} (format: {file_extension})")
        
        # Extract based on format
        if file_extension == '.pdf':
            text = self._extract_from_pdf(file_path)
        elif file_extension in ['.docx', '.doc']:
            text = self._extract_from_docx(file_path)
        else:
            raise ValueError(f"Handler not implemented for: {file_extension}")
        
        # Normalize if requested
        if clean and self.normalize_text:
            logger.info("Normalizing extracted text...")
            text = self.normalizer.normalize(text)
        
        return text
    
    
    def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF files"""
        try:
            logger.info(f"Extracting text from PDF: {file_path}")
            
            reader = PdfReader(file_path)
            num_pages = len(reader.pages)
            logger.info(f"PDF has {num_pages} pages")
            
            text = ""
            for page_num, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    logger.debug(f"Extracted {len(page_text)} chars from page {page_num}")
            
            if not text.strip():
                logger.warning("No text extracted from PDF - might be scanned/image-based")
                return ""
            
            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text
            
        except Exception as e:
            logger.error(f"Error extracting from PDF: {str(e)}")
            raise Exception(f"PDF extraction failed: {str(e)}")
    
    
    def _extract_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX/DOC files"""
        try:
            logger.info(f"Extracting text from DOCX: {file_path}")
            
            doc = docx.Document(file_path)
            
            text = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text.append(paragraph.text)
            
            full_text = "\n".join(text)
            
            if not full_text.strip():
                logger.warning("No text extracted from DOCX - file might be empty")
                return ""
            
            logger.info(f"Successfully extracted {len(full_text)} characters from DOCX")
            return full_text
            
        except Exception as e:
            logger.error(f"Error extracting from DOCX: {str(e)}")
            raise Exception(f"DOCX extraction failed: {str(e)}")
    
    
    def get_file_info(self, file_path: str) -> dict:
        """Get information about a file"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_stats = os.stat(file_path)
        file_extension = Path(file_path).suffix.lower()
        
        info = {
            'filename': os.path.basename(file_path),
            'extension': file_extension,
            'size_bytes': file_stats.st_size,
            'size_mb': round(file_stats.st_size / (1024 * 1024), 2),
            'is_supported': file_extension in self.supported_formats
        }
        
        return info
    
    
    def validate_contract_text(self, text: str, min_length: int = 100) -> dict:
        """
        Validate if extracted text looks like a contract
        
        Args:
            text: Extracted text
            min_length: Minimum character length
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'is_valid': False,
            'length_ok': False,
            'has_contract_keywords': False,
            'issues': []
        }
        
        # Check length
        if len(text) < min_length:
            result['issues'].append(f"Text too short ({len(text)} chars, need {min_length})")
            return result
        
        result['length_ok'] = True
        
        # Check for contract keywords
        contract_keywords = [
            'agreement', 'contract', 'party', 'parties',
            'terms', 'conditions', 'hereby', 'whereas',
            'signed', 'effective', 'termination'
        ]
        
        text_lower = text.lower()
        found_keywords = [kw for kw in contract_keywords if kw in text_lower]
        
        if len(found_keywords) < 2:
            result['issues'].append("Not enough contract keywords found")
            return result
        
        result['has_contract_keywords'] = True
        result['is_valid'] = True
        result['found_keywords'] = found_keywords
        
        return result
    
    
    def get_text_stats(self, text: str) -> dict:
        """
        Get statistics about extracted text
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary of statistics
        """
        words = text.split()
        sentences = [s for s in re.split(r'[.!?]+', text) if s.strip()]
        paragraphs = [p for p in text.split('\n\n') if p.strip()]
        
        return {
            'characters': len(text),
            'words': len(words),
            'sentences': len(sentences),
            'paragraphs': len(paragraphs),
            'avg_word_length': round(sum(len(w) for w in words) / len(words), 1) if words else 0,
            'avg_sentence_length': round(len(words) / len(sentences), 1) if sentences else 0
        }


# Example usage
if __name__ == "__main__":
    processor = ContractProcessor()
    
    print("=" * 60)
    print("CONTRACT PROCESSOR - COMPLETE VERSION")
    print("=" * 60)
    print()
    
    test_file = input("Enter path to test contract (PDF/DOCX): ").strip()
    
    if test_file:
        try:
            # Get file info
            info = processor.get_file_info(test_file)
            print(f"📄 File: {info['filename']}")
            print(f"📏 Size: {info['size_mb']} MB")
            print(f"📋 Type: {info['extension']}")
            print()
            
            # Extract text
            print("⏳ Extracting and cleaning text...")
            text = processor.extract_text(test_file, clean=True)
            
            print()
            print("✅ Extraction successful!")
            print()
            
            # Show statistics
            stats = processor.get_text_stats(text)
            print("📊 TEXT STATISTICS:")
            print(f"   Characters: {stats['characters']}")
            print(f"   Words: {stats['words']}")
            print(f"   Sentences: {stats['sentences']}")
            print(f"   Paragraphs: {stats['paragraphs']}")
            print(f"   Avg word length: {stats['avg_word_length']}")
            print(f"   Avg sentence length: {stats['avg_sentence_length']} words")
            print()
            
            # Validate
            validation = processor.validate_contract_text(text)
            print("✓ VALIDATION:")
            print(f"   Is valid contract: {validation['is_valid']}")
            if validation['is_valid']:
                print(f"   Found keywords: {', '.join(validation['found_keywords'][:5])}")
            else:
                print(f"   Issues: {', '.join(validation['issues'])}")
            print()
            
            # Preview
            print("=" * 60)
            print("PREVIEW (first 500 characters):")
            print("=" * 60)
            print(text[:500])
            if len(text) > 500:
                print(f"\n... (and {len(text) - 500} more characters)")
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    else:
        print("No file provided. Test skipped.")