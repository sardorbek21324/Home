"""
Universal compatibility layer for Aiogram exceptions.
Works for v2.x, v3.0-beta, v3.1+, and v3.4+.
"""

import importlib

MessageNotModified = None
TelegramBadRequest = None

# Try different import paths step-by-step
for path_set in [
    # aiogram v3.2–v3.4+
    ("aiogram.exceptions", ["MessageNotModified", "TelegramBadRequest"]),
    # aiogram 3.0.x beta and 3.1.x — they had slightly different names
    ("aiogram.exceptions", ["MessageNotModified", "BadRequest"]),
    # aiogram v2.x
    ("aiogram.utils.exceptions", ["MessageNotModified", "BadRequest"]),
]:
    module_name, names = path_set
    try:
        module = importlib.import_module(module_name)
        for name in names:
            if hasattr(module, name):
                obj = getattr(module, name)
                if name == "BadRequest":
                    TelegramBadRequest = obj
                elif name == "TelegramBadRequest":
                    TelegramBadRequest = obj
                elif name == "MessageNotModified":
                    MessageNotModified = obj
        if MessageNotModified and TelegramBadRequest:
            break
    except ModuleNotFoundError:
        continue
    except ImportError:
        continue

# Fallback definitions (no crash if both missing)
if MessageNotModified is None:
    class MessageNotModified(Exception):
        pass

if TelegramBadRequest is None:
    class TelegramBadRequest(Exception):
        pass
