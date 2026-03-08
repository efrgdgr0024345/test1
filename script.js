const calculatorPanel = document.getElementById('calculator-panel');
const panelSize = document.getElementById('panel-size');
const minimizeButton = document.getElementById('minimize-button');
const calcDisplay = document.getElementById('calc-display');
const calcGrid = document.getElementById('calc-grid');
const historyList = document.getElementById('history-list');
const clearHistoryButton = document.getElementById('clear-history');
const angleModeIndicator = document.getElementById('angle-mode-indicator');
const memoryIndicator = document.getElementById('memory-indicator');

const questionText = document.getElementById('question-text');
const answerInput = document.getElementById('answer-input');
const checkAnswerButton = document.getElementById('check-answer');
const newQuestionButton = document.getElementById('new-question');
const feedbackText = document.getElementById('feedback-text');
const scoreText = document.getElementById('score-text');

const FUNCTIONS = new Set(['sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sqrt', 'ln', 'log', 'abs']);
const CONSTANTS = { pi: Math.PI, e: Math.E };

let currentExpression = '0';
let lastAnswer = 0;
let memoryValue = 0;
let angleMode = 'DEG';

let currentQuestion = null;
let correctCount = 0;
let attemptCount = 0;

function toRadians(value) {
  return angleMode === 'DEG' ? (value * Math.PI) / 180 : value;
}

function fromRadians(value) {
  return angleMode === 'DEG' ? (value * 180) / Math.PI : value;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return 'Error';
  }
  const rounded = Number(value.toPrecision(12));
  return String(rounded);
}

function updateDisplay() {
  calcDisplay.value = currentExpression;
}

function updateStatus() {
  angleModeIndicator.textContent = `Mode: ${angleMode}`;
  memoryIndicator.textContent = `Memory: ${formatNumber(memoryValue)}`;
}

function appendHistory(expression, result, isError = false) {
  const item = document.createElement('li');
  const time = new Date().toLocaleTimeString();
  item.innerHTML = `<div class="history-time">${time} · ${angleMode}</div><div>${expression} = ${isError ? 'Error' : result}</div>`;
  historyList.prepend(item);
}

function getLastToken(expression) {
  const matches = expression.match(/(asin|acos|atan|sqrt|sin|cos|tan|ln|log|abs|pi|e|ans|\d*\.?\d+|[()+\-*/^%!])$/i);
  return matches ? matches[0] : '';
}

function shouldInsertMultiply(prevToken, nextToken) {
  const prevIsValue = /^(\d*\.?\d+|\)|pi|e|ans|!|%)$/i.test(prevToken);
  const nextStartsValue = /^(\d|\(|pi|e|ans|sin|cos|tan|asin|acos|atan|sqrt|ln|log|abs)/i.test(nextToken);
  return prevIsValue && nextStartsValue;
}

function clearDisplay() {
  currentExpression = '0';
  updateDisplay();
}

function deleteLastChar() {
  if (currentExpression === 'Error' || currentExpression.length <= 1) {
    clearDisplay();
    return;
  }
  currentExpression = currentExpression.slice(0, -1);
  updateDisplay();
}

function insertToken(token) {
  if (currentExpression === 'Error') {
    currentExpression = '0';
  }

  const prevToken = getLastToken(currentExpression);
  const needsMultiply = shouldInsertMultiply(prevToken, token);

  if (currentExpression === '0' && /^\d|\./.test(token)) {
    currentExpression = token;
  } else if (currentExpression === '0' && !['+', '-', '*', '/', '^', ')'].includes(token)) {
    currentExpression = token;
  } else {
    currentExpression += `${needsMultiply ? '*' : ''}${token}`;
  }

  updateDisplay();
}

function toggleSign() {
  if (currentExpression === 'Error') {
    clearDisplay();
    return;
  }

  if (currentExpression === '0') {
    currentExpression = '-';
  } else if (currentExpression.startsWith('-')) {
    currentExpression = currentExpression.slice(1);
  } else {
    currentExpression = `-${currentExpression}`;
  }

  updateDisplay();
}

function tokenize(expression) {
  const tokens = [];
  let i = 0;

  while (i < expression.length) {
    const ch = expression[i];

    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }

    if (/[0-9.]/.test(ch)) {
      let number = ch;
      i += 1;
      while (i < expression.length && /[0-9.]/.test(expression[i])) {
        number += expression[i];
        i += 1;
      }
      if (!/^\d*\.?\d+$/.test(number)) {
        throw new Error('Invalid number format');
      }
      tokens.push(number);
      continue;
    }

    if (/[a-z]/i.test(ch)) {
      let name = ch;
      i += 1;
      while (i < expression.length && /[a-z]/i.test(expression[i])) {
        name += expression[i];
        i += 1;
      }
      tokens.push(name.toLowerCase());
      continue;
    }

    if ('+-*/^()!%'.includes(ch)) {
      tokens.push(ch);
      i += 1;
      continue;
    }

    throw new Error('Unsupported character');
  }

  return tokens;
}

function toRpn(tokens) {
  const output = [];
  const operators = [];
  const precedence = { '+': 1, '-': 1, '*': 2, '/': 2, '^': 4, 'u-': 3, '!': 5, '%': 5 };
  const rightAssociative = new Set(['^', 'u-']);

  for (let idx = 0; idx < tokens.length; idx += 1) {
    const token = tokens[idx];
    const prev = tokens[idx - 1];

    if (/^\d*\.?\d+$/.test(token)) {
      output.push(token);
      continue;
    }

    if (token === 'ans') {
      output.push(String(lastAnswer));
      continue;
    }

    if (Object.hasOwn(CONSTANTS, token)) {
      output.push(String(CONSTANTS[token]));
      continue;
    }

    if (FUNCTIONS.has(token)) {
      operators.push(token);
      continue;
    }

    if (token === '(') {
      operators.push(token);
      continue;
    }

    if (token === ')') {
      while (operators.length && operators[operators.length - 1] !== '(') {
        output.push(operators.pop());
      }
      if (operators.pop() !== '(') {
        throw new Error('Mismatched parentheses');
      }
      if (operators.length && FUNCTIONS.has(operators[operators.length - 1])) {
        output.push(operators.pop());
      }
      continue;
    }

    let op = token;
    if (op === '-' && (!prev || '()+-*/^'.includes(prev))) {
      op = 'u-';
    }

    while (operators.length) {
      const top = operators[operators.length - 1];
      if (top === '(' || FUNCTIONS.has(top)) {
        break;
      }
      const higherPrec = precedence[top] > precedence[op];
      const equalPrec = precedence[top] === precedence[op];
      if (higherPrec || (equalPrec && !rightAssociative.has(op))) {
        output.push(operators.pop());
      } else {
        break;
      }
    }
    operators.push(op);
  }

  while (operators.length) {
    const op = operators.pop();
    if (op === '(' || op === ')') {
      throw new Error('Mismatched parentheses');
    }
    output.push(op);
  }

  return output;
}

function factorial(value) {
  if (!Number.isInteger(value) || value < 0 || value > 170) {
    throw new Error('Invalid factorial input');
  }
  let result = 1;
  for (let i = 2; i <= value; i += 1) {
    result *= i;
  }
  return result;
}

function applyFunction(name, value) {
  switch (name) {
    case 'sin':
      return Math.sin(toRadians(value));
    case 'cos':
      return Math.cos(toRadians(value));
    case 'tan':
      return Math.tan(toRadians(value));
    case 'asin':
      return fromRadians(Math.asin(value));
    case 'acos':
      return fromRadians(Math.acos(value));
    case 'atan':
      return fromRadians(Math.atan(value));
    case 'sqrt':
      if (value < 0) {
        throw new Error('Square root domain error');
      }
      return Math.sqrt(value);
    case 'ln':
      if (value <= 0) {
        throw new Error('Natural log domain error');
      }
      return Math.log(value);
    case 'log':
      if (value <= 0) {
        throw new Error('Log domain error');
      }
      return Math.log10(value);
    case 'abs':
      return Math.abs(value);
    default:
      throw new Error('Unknown function');
  }
}

function evaluateRpn(rpn) {
  const stack = [];

  for (const token of rpn) {
    if (/^[-+]?\d*\.?\d+(e[-+]?\d+)?$/i.test(token)) {
      stack.push(Number(token));
      continue;
    }

    if (FUNCTIONS.has(token)) {
      const value = stack.pop();
      if (value === undefined) {
        throw new Error('Invalid function arguments');
      }
      stack.push(applyFunction(token, value));
      continue;
    }

    if (token === 'u-') {
      const value = stack.pop();
      stack.push(-value);
      continue;
    }

    if (token === '!') {
      const value = stack.pop();
      stack.push(factorial(value));
      continue;
    }

    if (token === '%') {
      const value = stack.pop();
      stack.push(value / 100);
      continue;
    }

    const b = stack.pop();
    const a = stack.pop();
    if (a === undefined || b === undefined) {
      throw new Error('Invalid expression');
    }

    switch (token) {
      case '+':
        stack.push(a + b);
        break;
      case '-':
        stack.push(a - b);
        break;
      case '*':
        stack.push(a * b);
        break;
      case '/':
        if (b === 0) {
          throw new Error('Division by zero');
        }
        stack.push(a / b);
        break;
      case '^':
        stack.push(a ** b);
        break;
      default:
        throw new Error('Unknown operator');
    }
  }

  if (stack.length !== 1 || !Number.isFinite(stack[0])) {
    throw new Error('Evaluation error');
  }

  return stack[0];
}

function evaluateExpression() {
  try {
    const input = currentExpression;
    const tokens = tokenize(input);
    const rpn = toRpn(tokens);
    const result = evaluateRpn(rpn);
    const formatted = formatNumber(result);
    appendHistory(input, formatted);
    currentExpression = formatted;
    lastAnswer = result;
    updateDisplay();
    updateStatus();
  } catch {
    appendHistory(currentExpression, 'Error', true);
    currentExpression = 'Error';
    updateDisplay();
  }
}

function withCurrentValue(action) {
  try {
    const value = currentExpression === 'Error' ? 0 : evaluateRpn(toRpn(tokenize(currentExpression)));
    return action(value);
  } catch {
    return action(0);
  }
}

function onCalculatorAction(action) {
  switch (action) {
    case 'clear':
      clearDisplay();
      break;
    case 'delete':
      deleteLastChar();
      break;
    case 'evaluate':
      evaluateExpression();
      break;
    case 'toggle-sign':
      toggleSign();
      break;
    case 'percent':
      insertToken('%');
      break;
    case 'factorial':
      insertToken('!');
      break;
    case 'square':
      currentExpression = `(${currentExpression})^2`;
      updateDisplay();
      break;
    case 'inverse':
      currentExpression = `1/(${currentExpression})`;
      updateDisplay();
      break;
    case 'mode-toggle':
      angleMode = angleMode === 'DEG' ? 'RAD' : 'DEG';
      updateStatus();
      break;
    case 'ans':
      insertToken('ans');
      break;
    case 'memory-clear':
      memoryValue = 0;
      updateStatus();
      break;
    case 'memory-recall':
      insertToken(formatNumber(memoryValue));
      break;
    case 'memory-add':
      withCurrentValue((value) => {
        memoryValue += value;
        updateStatus();
      });
      break;
    case 'memory-subtract':
      withCurrentValue((value) => {
        memoryValue -= value;
        updateStatus();
      });
      break;
    default:
      break;
  }
}

function handleCalculatorButtonClick(event) {
  const button = event.target.closest('button');
  if (!button) {
    return;
  }

  const { action, token } = button.dataset;
  if (action) {
    onCalculatorAction(action);
  } else if (token) {
    insertToken(token);
  }
}

function handleKeyboard(event) {
  if (document.activeElement === answerInput) {
    return;
  }

  if (/^[0-9]$/.test(event.key) || ['+', '-', '*', '/', '^', '(', ')', '.'].includes(event.key)) {
    insertToken(event.key);
    return;
  }

  if (event.key === 'Enter') {
    evaluateExpression();
    return;
  }

  if (event.key === 'Backspace') {
    deleteLastChar();
    return;
  }

  if (event.key === 'Escape') {
    clearDisplay();
  }
}

function newQuestion() {
  const a = Math.floor(Math.random() * 31) + 1;
  const b = Math.floor(Math.random() * 29) + 1;
  const operatorPool = ['+', '-', '*', '/'];
  const operator = operatorPool[Math.floor(Math.random() * operatorPool.length)];

  const answerMap = {
    '+': a + b,
    '-': a - b,
    '*': a * b,
    '/': Number((a / b).toFixed(3))
  };

  currentQuestion = { text: `${a} ${operator} ${b}`, answer: answerMap[operator] };
  questionText.textContent = `Solve: ${currentQuestion.text}`;
  feedbackText.textContent = '';
  answerInput.value = '';
  answerInput.focus();
}

function updateScore() {
  scoreText.textContent = `Score: ${correctCount} correct, ${attemptCount} attempted`;
}

function checkAnswer() {
  if (!currentQuestion) {
    feedbackText.textContent = 'Create a question first.';
    return;
  }

  const userValue = Number(answerInput.value);
  if (Number.isNaN(userValue)) {
    feedbackText.textContent = 'Please enter a valid number.';
    return;
  }

  attemptCount += 1;
  const isCorrect = Math.abs(userValue - currentQuestion.answer) < 0.001;

  if (isCorrect) {
    correctCount += 1;
    feedbackText.textContent = 'Correct! Great job.';
  } else {
    feedbackText.textContent = `Not quite. Correct answer: ${currentQuestion.answer}`;
  }

  updateScore();
}

panelSize.addEventListener('input', () => {
  calculatorPanel.style.width = `${panelSize.value}px`;
});

minimizeButton.addEventListener('click', () => {
  const minimized = calculatorPanel.classList.toggle('minimized');
  minimizeButton.textContent = minimized ? 'Expand' : 'Minimize';
  minimizeButton.setAttribute('aria-expanded', String(!minimized));
});

calcGrid.addEventListener('click', handleCalculatorButtonClick);
window.addEventListener('keydown', handleKeyboard);

clearHistoryButton.addEventListener('click', () => {
  historyList.innerHTML = '';
});

checkAnswerButton.addEventListener('click', checkAnswer);
newQuestionButton.addEventListener('click', newQuestion);
answerInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    checkAnswer();
  }
});

updateDisplay();
updateStatus();
updateScore();
