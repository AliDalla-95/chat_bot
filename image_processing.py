""" ali """
import pytesseract
from PIL import Image

def check_text_in_image(image_path, required_text):
    """ ali """
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang='eng+ara')  # Detect English & Arabic
    return required_text in text and ("Follow" in text)
