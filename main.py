import os
import bot
import ocr_processor
import subprocess

process1 = subprocess.Popen(['python', 'bot.py'], preexec_fn=os.setsid)
process2 = subprocess.Popen(['python', 'ocr_processor.py'], preexec_fn=os.setsid)
