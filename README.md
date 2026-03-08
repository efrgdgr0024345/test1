# Math Training Lab

A browser-based math practice app with a rebuilt scientific calculator and training workspace.

## Features

- Completely rebuilt scientific calculator with a proper clickable number pad and operator grid
- Two-line display (expression + evaluated result)
- Degree/Radian toggle for trig operations
- Scientific keys: `sin`, `cos`, `tan`, `ln`, `log`, `√`, `x²`, `xʸ`, `1/x`, `%`, `±`, `π`, `e`, `Ans`, `x!`
- Memory workflow: `MC`, `MR`, `M+`, `M-`
- Keyboard support for numbers/operators + Enter/Escape/Backspace
- Timestamped calculation history
- Resizable and minimizable calculator panel on the left
- Math training quiz with random arithmetic questions and score tracking

## Run locally

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.
