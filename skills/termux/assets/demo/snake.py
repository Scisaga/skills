#!/usr/bin/env python3
"""A small, offline Snake game for the Termux Linux desktop.

Run inside Debian/Xfce: python3 snake.py
If Tk is missing: sudo apt-get install python3-tk
Controls: arrow keys or WASD; Space pauses; R restarts; Esc closes.
"""

import random
from collections import deque

try:
    import tkinter as tk
except ImportError as error:
    raise SystemExit("Tk is missing. In Debian, run: sudo apt-get install python3-tk") from error

COLS, ROWS, CELL = 24, 16, 60
BG, BOARD, GRID = "#111923", "#172331", "#203041"
MINT, HEAD, FOOD = "#80cbb7", "#b5f0d2", "#ffc877"
TEXT, MUTED = "#eef4fb", "#9cb1c9"


class Snake:
    def __init__(self):
        self.body = deque([(5, 8), (4, 8), (3, 8)])
        self.direction = self.pending = (1, 0)
        self.food, self.score = (12, 8), 0
        self.state = "ready"
        self.random = random.Random(7)

    def turn(self, direction):
        if direction != (-self.direction[0], -self.direction[1]):
            self.pending = direction
            if self.state == "ready":
                self.state = "running"

    def tick(self):
        if self.state != "running":
            return
        self.direction = self.pending
        x, y = self.body[0]
        dx, dy = self.direction
        head = (x + dx, y + dy)
        eating = head == self.food
        occupied = set(self.body if eating else list(self.body)[:-1])
        if not (0 <= head[0] < COLS and 0 <= head[1] < ROWS) or head in occupied:
            self.state = "over"
            return
        self.body.appendleft(head)
        if eating:
            self.score += 1
            free = [(x, y) for y in range(ROWS) for x in range(COLS)
                    if (x, y) not in self.body]
            self.food = self.random.choice(free) if free else None
            if not free:
                self.state = "won"
        else:
            self.body.pop()


class App:
    def __init__(self):
        self.game = Snake()
        self.best_score = 0
        self.root = tk.Tk()
        self.root.title("Snake | Python on Termux")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(self.root, width=COLS * CELL + 120,
                                height=ROWS * CELL + 264, bg=BG,
                                highlightthickness=0)
        self.canvas.pack()
        self.root.bind("<KeyPress>", self.key)
        self.draw()
        self.root.after(170, self.update)

    def key(self, event):
        key = event.keysym.lower()
        turns = {"up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1),
                 "left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0)}
        if key in turns:
            self.game.turn(turns[key])
        elif key == "space" and self.game.state in ("running", "paused"):
            self.game.state = "paused" if self.game.state == "running" else "running"
        elif key == "r":
            self.game = Snake()
        elif key == "escape":
            self.root.destroy()
            return
        self.draw()

    def label(self, x, y, text, size, color=TEXT, anchor="w", bold=False):
        self.canvas.create_text(x, y, text=text, fill=color, anchor=anchor,
                                font=("DejaVu Sans", -size, "bold" if bold else "normal"))

    def draw(self):
        c, g = self.canvas, self.game
        c.delete("all")
        width = COLS * CELL + 120
        self.label(60, 47, "SCISAGA  /  PYTHON DEMO", 23, MUTED)
        self.label(60, 111, "Snake", 60, bold=True)
        self.label(width - 60, 102, f"SCORE   {g.score:02d}", 37, MINT, "e", True)
        self.label(width - 60, 148, f"BEST   {self.best_score:02d}", 24, MUTED, "e", True)
        top, left = 180, 60
        c.create_rectangle(left, top, left + COLS * CELL, top + ROWS * CELL,
                           fill=BOARD, outline=GRID, width=2)
        for x in range(1, COLS):
            c.create_line(left + x * CELL, top, left + x * CELL, top + ROWS * CELL,
                          fill=GRID)
        for y in range(1, ROWS):
            c.create_line(left, top + y * CELL, left + COLS * CELL, top + y * CELL,
                          fill=GRID)
        if g.food:
            fx, fy = left + (g.food[0] + .5) * CELL, top + (g.food[1] + .5) * CELL
            c.create_oval(fx - 17, fy - 17, fx + 17, fy + 17, fill=FOOD, outline="")
            c.create_oval(fx - 5, fy - 10, fx + 3, fy - 2, fill="#ffe4b8", outline="")
        for i, (x, y) in enumerate(g.body):
            x, y = left + x * CELL, top + y * CELL
            c.create_rectangle(x + 4, y + 4, x + CELL - 4, y + CELL - 4,
                               fill=HEAD if i == 0 else MINT, outline="")
            if i == 0:
                dx, dy = g.direction
                for side in (-1, 1):
                    ex = x + CELL / 2 + dx * 13 - dy * side * 11
                    ey = y + CELL / 2 + dy * 13 + dx * side * 11
                    c.create_oval(ex - 4, ey - 4, ex + 4, ey + 4, fill=BG, outline="")
        messages = {"ready": "Press an arrow key to start", "paused": "Paused · Space to resume",
                    "over": "Game over · R to restart", "won": "Board complete · R to restart"}
        if g.state in messages:
            cx, cy = width / 2, top + ROWS * CELL / 2
            c.create_rectangle(cx - 370, cy - 52, cx + 370, cy + 52,
                               fill=BG, outline="#3b5168", width=2)
            self.label(cx, cy, messages[g.state], 32, anchor="center")
        self.label(60, top + ROWS * CELL + 44, "Arrow keys / WASD   ·   Space: pause   ·   R: restart", 24, MUTED)
        self.label(width - 60, top + ROWS * CELL + 44, "Python + Tk", 24, MINT, "e")

    def update(self):
        self.game.tick()
        self.best_score = max(self.best_score, self.game.score)
        self.draw()
        self.root.after(170, self.update)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print("Starting Snake — Python + Tk, running locally.", flush=True)
    App().run()
