import json
import os
import getpass
import platform
from pathlib import Path

def get_config_dir():
    """Get the appropriate config directory based on the operating system"""
    system = platform.system()
    
    if system == "Linux":
        # Use ~/.config/netschool-cli on Linux
        config_dir = os.path.expanduser("~/.config/netschool-cli")
    elif system == "Windows":
        # Use %APPDATA%\netschool-cli on Windows
        config_dir = os.path.join(os.environ.get("APPDATA", ""), "netschool-cli")
    else:
        # Fallback to current directory for other systems
        config_dir = os.path.join(os.getcwd(), ".config", "netschool-cli")
    
    # Create the directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

# Define the config file path
CONFIG_FILE = os.path.join(get_config_dir(), "config.json")

def load_config():
    """Load configuration from JSON file or create new one if it doesn't exist"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config
        except json.JSONDecodeError:
            # print(f"Ошибка чтения файла конфигурации {CONFIG_FILE}. Создается новый.")
            return create_config()
    else:
        return create_config()

def create_config():
    print("=== Первый запуск программы ===")
    print("Пожалуйста, введите данные для входа в Сетевой Город:")
    
    username = input("Имя пользователя: ")
    password = getpass.getpass("Пароль: ")
    school = input("ID школы или название школы: ")
    try: school = int(school)
    except ValueError: pass
    
    config = {
        "username": username,
        "password": password,
        "school": school
    }
    
    # Save configuration to file
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    
    print(f"Конфигурация сохранена. В следующий раз Вам не придется вводить данные заново.")
    return config

def get_credentials():
    config = load_config()
    return config["username"], config["password"], config["school"] 