# Math Training Lab

A browser-based math practice app with an advanced scientific calculator and training workspace.

## Features

- High-function scientific calculator with:
  - Trigonometric and inverse trig functions (`sin`, `cos`, `tan`, `asin`, `acos`, `atan`)
  - Logs and roots (`ln`, `log`, `sqrt`, `abs`)
  - Powers and post-fix operations (`x^y`, `x²`, `x!`, `%`, `1/x`, `±`)
  - Constants and stored values (`π`, `e`, `Ans`)
  - Memory controls (`MC`, `MR`, `M+`, `M-`)
  - Degree/Radian mode toggle for trig calculations
- Expression parser based on tokenization + RPN evaluation (no direct `eval`)
- Resizable + minimizable calculator panel on the left side
- Timestamped calculation history with mode context
- Math training quiz with random arithmetic questions and score tracking

## Run locally

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.
