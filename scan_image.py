from PIL import Image
import pytesseract
import requests
import time
import logging
import os
import re
# Load the image
image_path = 'Images/ali1.jpg'
image = Image.open(image_path)
width, height = image.size
# Define the region of interest (ROI) as (left, top, right, bottom)
# These coordinates define the rectangle you want to extract text from
# roi = (100, 100, 400, 200)  # Example coordinates, adjust as needed
roi = (
    0,    # بداية من أقصى اليسار
    0,                # بداية من أعلى الصورة
    int(2*width/3),  # نهاية عند ثلثي العرض من اليسار
    int(height*0.5)   # نهاية عند 30% من الارتفاع من الأعلى
)
# Crop the image to the region of interest
cropped_image = image.crop(roi)


# تحويل الصورة إلى تدرجات الرمادي وتحسين التباين
cropped_image = cropped_image.convert('L').point(lambda x: 0 if x < 128 else 255, '1')

# Use pytesseract to extract text from the cropped image
extracted_text = pytesseract.image_to_string(cropped_image)

# Print the extracted text
print("Extracted Text:")
print(extracted_text)


def check_text_in_image(image_path, chosen_words):

    if isinstance(chosen_words, str):
        chosen_words = [chosen_words]
    image_path = 'image_path'
    image = Image.open(image_path)
    width, height = image.size
    # Define the region of interest (ROI) as (left, top, right, bottom)
    # These coordinates define the rectangle you want to extract text from
    # roi = (100, 100, 400, 200)  # Example coordinates, adjust as needed
    roi = (
        0,    # بداية من أقصى اليسار
        0,                # بداية من أعلى الصورة
        int(2*width/3),  # نهاية عند ثلثي العرض من اليسار
        int(height*0.5)   # نهاية عند 30% من الارتفاع من الأعلى
    )
    # Crop the image to the region of interest
    cropped_image = image.crop(roi)


    # تحويل الصورة إلى تدرجات الرمادي وتحسين التباين
    cropped_image = cropped_image.convert('L').point(lambda x: 0 if x < 128 else 255, '1')

    # Use pytesseract to extract text from the cropped image
    extracted_text = pytesseract.image_to_string(cropped_image)

    for word in chosen_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        # print(f"word:{word}")
        if not re.search(pattern, extracted_text, re.IGNORECASE | re.UNICODE):
            return False 
        
        # Check if "Subscribed" is in the OCR text
    if not re.search(r'\bSubscribed\b|\bتم الاشتراك\b|\bВы подписаны\b', extracted_text, re.IGNORECASE | re.UNICODE):
        return False #, words_with_numbers
    # Print the extracted text
    print("Extracted Text:")
    print(extracted_text)
    return True 