from src.ui import run_screen
from src.ui_discovery import render

run_screen(lambda db,rows,total,cost: render(db))
