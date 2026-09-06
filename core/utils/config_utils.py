from ruamel.yaml import YAML
import threading

CONFIG_PATH = 'config.yaml'
lock = threading.Lock()

yaml = YAML()
yaml.preserve_quotes = True

# -----------------------
# load & update config
# -----------------------

import os
from dotenv import load_dotenv

load_dotenv()

ENV_MAPPING = {
    "api.key": "API_KEY",
    "api.huggingface_token": "HUGGINGFACE_TOKEN",
    "whisper.whisperX_302_api_key": "WHISPERX_302_API_KEY",
    "whisper.elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "sf_fish_tts.api_key": "SF_FISH_TTS_API_KEY",
    "openai_tts.api_key": "OPENAI_TTS_API_KEY",
    "azure_tts.api_key": "AZURE_TTS_API_KEY",
    "fish_tts.api_key": "FISH_TTS_API_KEY",
    "sf_cosyvoice2.api_key": "SF_COSYVOICE2_API_KEY",
    "f5tts.302_api": "F5TTS_302_API"
}

def load_key(key):
    # Check if the key has a corresponding environment variable
    if key in ENV_MAPPING:
        env_val = os.getenv(ENV_MAPPING[key])
        if env_val and env_val.strip():
            return env_val

    with lock:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            data = yaml.load(file)

    keys = key.split('.')
    value = data
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            raise KeyError(f"Key '{k}' not found in configuration")
    return value

def update_key(key, new_value):
    with lock:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            data = yaml.load(file)

        keys = key.split('.')
        current = data
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False

        if isinstance(current, dict) and keys[-1] in current:
            current[keys[-1]] = new_value
            with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                yaml.dump(data, file)
            return True
        else:
            raise KeyError(f"Key '{keys[-1]}' not found in configuration")
        
# basic utils
def get_joiner(language):
    if language in load_key('language_split_with_space'):
        return " "
    elif language in load_key('language_split_without_space'):
        return ""
    else:
        raise ValueError(f"Unsupported language code: {language}")

if __name__ == "__main__":
    print(load_key('language_split_with_space'))
