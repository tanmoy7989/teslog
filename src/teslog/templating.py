import pathlib

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = pathlib.Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
