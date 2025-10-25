import configparser
import os

def get_project_root():
    """Returns the absolute path to the project's root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_config():
    """
    Loads the configuration from the config.ini file in the project root.

    Returns:
        configparser.ConfigParser: The loaded configuration object.
    """
    project_root = get_project_root()
    config_path = os.path.join(project_root, 'config.ini')

    config = configparser.ConfigParser()
    config.read(config_path)

    if not config.sections():
        raise FileNotFoundError(f"Could not find or read the config file at: {config_path}")

    # Ensure the data directory exists
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)

    return config

# Load the config globally so it can be imported by other modules
config = load_config()
