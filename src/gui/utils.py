import os
import sys

def get_resource_path(filename):
    try:
        base_path = sys._MEIPASS  # type: ignore
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, filename)

class RedirectText:
    def __init__(self, output_callback):
        self.output_callback = output_callback
        self.last_line = ""

    def write(self, string):
        cleaned_string = string.replace('\r', '').replace('\n', '').strip()
        if cleaned_string:
            self.output_callback(cleaned_string + '\n')

    def flush(self):
        pass
