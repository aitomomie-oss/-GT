from src.ui import run_screen
from src.ui_evaluation_audit import render

run_screen(lambda db,rows,total,cost: render(db))
