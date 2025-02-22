import os
import time
import logging
import re
from PIL import Image
import pytesseract
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OCRHandler(FileSystemEventHandler):
    VALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp')
    
    def __init__(self):
        os.makedirs('outputs', exist_ok=True)
        
    def on_created(self, event):
        if not event.is_directory:
            file_path = event.src_path
            if file_path.lower().endswith(self.VALID_EXTENSIONS):
                logger.info("Processing new file: %s", file_path)
                result = check_text_in_image(file_path, ["Subscribed"])
                if result:
                    logger.info("Valid subscription found in: %s", file_path)
                else:
                    logger.warning("No valid subscription found in: %s", file_path)

def preprocess_image(image):
    """Enhance image for better OCR results"""
    # Convert to grayscale
    gray = image.convert('L')
    
    # Apply thresholding
    threshold = gray.point(lambda x: 0 if x < 180 else 255, '1')
    
    return threshold

def check_text_in_image(image_path, chosen_words):
    """Process image and check for specified words"""
    try:
        # Open and preprocess image
        with Image.open(image_path) as img:
            width, height = img.size
            
            # Define ROI (left, top, right, bottom)
            roi = (
                0,                   # Start from left edge
                int(height * 0.1),    # Start 10% from top
                int(width * 0.8),     # End 80% from left
                int(height * 0.9)     # End 90% from top
            )
            
            cropped = img.crop(roi)
            processed = preprocess_image(cropped)
            
            # Perform OCR with multiple languages
            extracted_text = pytesseract.image_to_string(
                processed,
                lang='eng+ara+rus',  # English, Arabic, Russian
                config='--psm 6 --oem 3'
            )

        logger.debug("Extracted text:\n%s", extracted_text)
        
        if isinstance(chosen_words, str):
            chosen_words = [chosen_words]

        # Check for required words
        for word in chosen_words:
            pattern = re.compile(r'\b' + re.escape(word) + r'\b', 
                                flags=re.IGNORECASE | re.UNICODE)
            if not pattern.search(extracted_text):
                return False

        # Verify subscription text in multiple languages
        subscription_pattern = re.compile(
            r'\b(Subscribed|تم الاشتراك|Вы подписаны)\b',
            flags=re.IGNORECASE | re.UNICODE
        )
        
        if not subscription_pattern.search(extracted_text):
            return False

        return True

    except Exception as e:
        logger.error("Processing error: %s", str(e))
        return False

def start_monitoring(path_to_watch):
    observer = Observer()
    event_handler = OCRHandler()
    observer.schedule(event_handler, path_to_watch, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    # Example usage
    test_image = "test_image.jpg"
    if check_text_in_image(test_image, ["Special", "Offer"]):
        print("Required text found!")
    
    # Start monitoring folder
    start_monitoring("./watch_folder")