import requests
import time
import logging
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FreeOCRProcessor:
    def __init__(self):
        self.base_url = "https://api.ocr.space/parse/image"
        self.public_key = "K84097137188957"  # Public demo key
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.hourly_limit = 300
        self.request_count = 0
        self.last_reset = time.time()

    def _reset_counter(self):
        current_time = time.time()
        if current_time - self.last_reset > 3600:
            self.request_count = 0
            self.last_reset = current_time

    def process_image(self, image_path, language="eng"):
        self._reset_counter()
        
        if self.request_count >= self.hourly_limit:
            logger.warning("Hourly rate limit reached")
            return None

        for attempt in range(self.max_retries):
            try:
                with open(image_path, 'rb') as f:
                    response = requests.post(
                        self.base_url,
                        files={"file": f},
                        data={
                            "apikey": self.public_key,
                            "language": language,
                            "isOverlayRequired": False,
                            "OCREngine": 1
                        },
                        timeout=10
                    )

                self.request_count += 1

                if response.status_code == 200:
                    result = response.json()
                    if 'ParsedResults' in result:
                        return result['ParsedResults'][0]['ParsedText']
                    else:
                        logger.error("API error: %s", result.get('ErrorMessage', 'Unknown error'))
                        return None

                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning("Rate limited. Retrying after %s seconds", retry_after)
                    time.sleep(retry_after)
                    continue

                else:
                    logger.error("API error: HTTP %s", response.status_code)
                    return None

            except requests.exceptions.RequestException as e:
                logger.error("Request failed: %s", str(e))
                time.sleep(self.retry_delay * (attempt + 1))
                continue

        return None

class OCRHandler(FileSystemEventHandler):
    VALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.pdf')

    def __init__(self, processor):
        self.processor = processor
        os.makedirs('outputs', exist_ok=True)

    def on_created(self, event):
        if not event.is_directory:
            file_path = event.src_path
            if file_path.lower().endswith(self.VALID_EXTENSIONS):
                logger.info("Processing new file: %s", file_path)
                text = self.processor.process_image(file_path)
                if text:
                    output_file = f"outputs/{os.path.basename(file_path)}_result.txt"
                    with open(output_file, 'w') as f:
                        f.write(text)
                    logger.info("Saved results to: %s", output_file)
                else:
                    logger.warning("OCR failed for: %s", file_path)

    # ===== TEMPORARY TEST CODE =====
    # Uncomment these 3 lines to test a single image

def check_text_in_image(image_path, chosen_words):
    """
    Processes an image with OCR and checks if the chosen words are present.
    
    :param image_path: Path to the image file.
    :param chosen_words: A string (for one word) or a list of words to check.
    :return: True if all chosen words are found in the OCR text, False otherwise.
    """
    # Run OCR on the image
    # ocr_processor = FreeOCRProcessor()
    # ocr_text = ocr_processor.process_image(image_path)
    # If OCR fails, return False
    ocr_processor = FreeOCRProcessor()
    ocr_text = ""
    
    for lang in ["eng", "ara", "rus"]:  # Check all three languages
        text = ocr_processor.process_image(image_path, lang)
        if text:
            ocr_text += " " + text  # Combine results from all languages
            
    if not ocr_text:
        return False
    # print(f"{ocr_text}")
    # Ensure chosen_words is a list
    if isinstance(chosen_words, str):
        chosen_words = [chosen_words]

    # Option 1: Using simple substring search (case-insensitive)
    # if all(word.lower() in ocr_text.lower() for word in chosen_words):
    #     return True
    # else:
    #     return False
    # Option 2: Using regular expressions for whole-word matching
    # print(f"chosen_words: {chosen_words}")
    for word in chosen_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        # print(f"word:{word}")
        if not re.search(pattern, ocr_text, re.IGNORECASE | re.UNICODE):
            return False
        
        # Check if "Subscribed" is in the OCR text
    if not re.search(r'\bSubscribed\b|\bتم الاشتراك\b|\bВы подписаны\b', ocr_text, re.IGNORECASE | re.UNICODE):
        return False
    
    return True    
# if __name__ == "__main__":
#     pass





    # ===== FOLDER MONITORING CODE =====
    # Keep this for automatic processing
    # WATCH_FOLDER = "./watch_folder"
    # OUTPUT_FOLDER = "./outputs"
    
    # os.makedirs(WATCH_FOLDER, exist_ok=True)
    # os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # processor = FreeOCRProcessor()
    # event_handler = OCRHandler(processor)
    # observer = Observer()
    # observer.schedule(event_handler, path=WATCH_FOLDER, recursive=False)
    # observer.start()

    # try:
    #     logger.info(f"Monitoring folder: {os.path.abspath(WATCH_FOLDER)}")
    #     logger.info(f"Output folder: {os.path.abspath(OUTPUT_FOLDER)}")
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     observer.stop()
    # observer.join()