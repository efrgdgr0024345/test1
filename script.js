const calculatorPanel = document.getElementById('calculator-panel');
const panelSize = document.getElementById('panel-size');
const minimizeButton = document.getElementById('minimize-button');
const expressionDisplay = document.getElementById('expression-display');
const resultDisplay = document.getElementById('result-display');
const keypad = document.getElementById('keypad');
const modeButton = document.querySelector('button[data-action="mode"]');
const modeIndicator = document.getElementById('mode-indicator');
const memoryIndicator = document.getElementById('memory-indicator');
const historyList = document.getElementById('history-list');
const clearHistoryButton = document.getElementById('clear-history');

const questionText = document.getElementById('question-text');
const answerInput = document.getElementById('answer-input');
const checkAnswerButton = document.getElementById('check-answer');
const newQuestionButton = document.getElementById('new-question');
const feedbackText = document.getElementById('feedback-text');
const scoreText = document.getElementById('score-text');

let expression = '0';
let memoryValue = 0;
let lastAnswer = 0;
let angleMode = 'DEG';

let currentQuestion = null;
let correctCount = 0;
let attemptCount = 0;

function toRadians(value) {
  return angleMode === 'DEG' ? (value * Math.PI) / 180 : value;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    throw new Error('Invalid number');
  }
  return String(Number(value.toPrecision(12)));
}

function updateCalculatorUi(result = null) {
  expressionDisplay.textContent = expression;
  resultDisplay.textContent = result === null ? expression : result;
  modeIndicator.textContent = `Mode: ${angleMode}`;
  modeButton.textContent = angleMode;
  memoryIndicator.textContent = `M: ${formatNumber(memoryValue)}`;
}

function appendHistory(entry, isError = false) {
  const item = document.createElement('li');
  const time = new Date().toLocaleTimeString();
  item.innerHTML = `<div class="history-meta">${time} · ${angleMode}</div><div>${entry}${isError ? ' = Error' : ''}</div>`;
  historyList.prepend(item);
}

function normalizeExpression(input) {
  return input
    .replace(/\bpi\b/g, 'Math.PI')
    .replace(/\be\b/g, 'Math.E')
    .replace(/\bans\b/g, String(lastAnswer))
    .replace(/sin\(/g, 'sin(')
    .replace(/cos\(/g, 'cos(')
    .replace(/tan\(/g, 'tan(')
    .replace(/ln\(/g, 'ln(')
    .replace(/log\(/g, 'log(')
    .replace(/√\(/g, 'sqrt(')
    .replace(/\^/g, '**');
}

function safeEvaluate(rawExpression) {
  const normalized = normalizeExpression(rawExpression);

  const safe = normalized
    .replace(/sin\(([^)]+)\)/g, (_, x) => `Math.sin(${angleMode === 'DEG' ? `(${x})*Math.PI/180` : x})`)
    .replace(/cos\(([^)]+)\)/g, (_, x) => `Math.cos(${angleMode === 'DEG' ? `(${x})*Math.PI/180` : x})`)
    .replace(/tan\(([^)]+)\)/g, (_, x) => `Math.tan(${angleMode === 'DEG' ? `(${x})*Math.PI/180` : x})`)
    .replace(/ln\(([^)]+)\)/g, 'Math.log($1)')
    .replace(/log\(([^)]+)\)/g, 'Math.log10($1)')
    .replace(/sqrt\(([^)]+)\)/g, 'Math.sqrt($1)');

  if (!/^[0-9+\-*/().,%\sA-Za-z_]*$/.test(safe)) {
    throw new Error('Unsafe expression');
  }

  // eslint-disable-next-line no-new-func
  const value = Function(`"use strict"; return (${safe});`)();
  if (!Number.isFinite(value)) {
    throw new Error('Math error');
  }
  return value;
}

function insertToken(token) {
  if (expression === '0' && /[0-9.]/.test(token)) {
    expression = token;
  } else if (expression === '0' && !['+', '-', '*', '/', '^', ')'].includes(token)) {
    expression = token;
  } else {
    expression += token;
  }
  updateCalculatorUi();
}

function evaluateNow() {
  try {
    const value = safeEvaluate(expression);
    const formatted = formatNumber(value);
    appendHistory(`${expression} = ${formatted}`);
    expression = formatted;
    lastAnswer = value;
    updateCalculatorUi(formatted);
  } catch {
    appendHistory(expression, true);
    expression = '0';
    resultDisplay.textContent = 'Error';
  }
}

function setUnaryWrap(fnName) {
  expression = `${fnName}(${expression})`;
  updateCalculatorUi();
}

function onAction(action) {
  switch (action) {
    case 'all-clear':
      expression = '0';
      updateCalculatorUi();
      break;
    case 'delete':
      expression = expression.length > 1 ? expression.slice(0, -1) : '0';
      updateCalculatorUi();
      break;
    case 'evaluate':
      evaluateNow();
      break;
    case 'mode':
      angleMode = angleMode === 'DEG' ? 'RAD' : 'DEG';
      updateCalculatorUi();
      break;
    case 'percent':
      expression = `(${expression})/100`;
      updateCalculatorUi();
      break;
    case 'sqrt':
      setUnaryWrap('sqrt');
      break;
    case 'sin':
    case 'cos':
    case 'tan':
    case 'ln':
    case 'log':
      setUnaryWrap(action);
      break;
    case 'square':
      expression = `(${expression})^2`;
      updateCalculatorUi();
      break;
    case 'inverse':
      expression = `1/(${expression})`;
      updateCalculatorUi();
      break;
    case 'sign':
      expression = expression.startsWith('-') ? expression.slice(1) : `-${expression}`;
      updateCalculatorUi();
      break;
    case 'factorial':
      expression = `fact(${expression})`;
      updateCalculatorUi();
      break;
    case 'ans':
      insertToken('ans');
      break;
    case 'memory-clear':
      memoryValue = 0;
      updateCalculatorUi();
      break;
    case 'memory-recall':
      insertToken(formatNumber(memoryValue));
      break;
    case 'memory-add':
      memoryValue += safeEvaluate(expression);
      updateCalculatorUi();
      break;
    case 'memory-subtract':
      memoryValue -= safeEvaluate(expression);
      updateCalculatorUi();
      break;
    default:
      break;
  }
}

keypad.addEventListener('click', (event) => {
  const btn = event.target.closest('button');
  if (!btn) {
    return;
  }

  const token = btn.dataset.token;
  const action = btn.dataset.action;

  if (token) {
    insertToken(token);
    return;
  }

  if (action === 'factorial') {
    try {
      const value = safeEvaluate(expression);
      if (!Number.isInteger(value) || value < 0 || value > 170) {
        throw new Error('Factorial domain');
      }
      let total = 1;
      for (let i = 2; i <= value; i += 1) {
        total *= i;
      }
      expression = formatNumber(total);
      appendHistory(`${value}! = ${expression}`);
      updateCalculatorUi();
      lastAnswer = total;
    } catch {
      resultDisplay.textContent = 'Error';
      expression = '0';
      updateCalculatorUi();
    }
    return;
  }

  try {
    onAction(action);
  } catch {
    resultDisplay.textContent = 'Error';
    expression = '0';
  }
});

window.addEventListener('keydown', (event) => {
  if (document.activeElement === answerInput) {
    return;
  }

  if (/^[0-9]$/.test(event.key) || ['+', '-', '*', '/', '^', '(', ')', '.'].includes(event.key)) {
    insertToken(event.key);
  } else if (event.key === 'Enter') {
    evaluateNow();
  } else if (event.key === 'Backspace') {
    expression = expression.length > 1 ? expression.slice(0, -1) : '0';
    updateCalculatorUi();
  } else if (event.key === 'Escape') {
    expression = '0';
    updateCalculatorUi();
  }
});

panelSize.addEventListener('input', () => {
  calculatorPanel.style.width = `${panelSize.value}px`;
});

minimizeButton.addEventListener('click', () => {
  const minimized = calculatorPanel.classList.toggle('minimized');
  minimizeButton.textContent = minimized ? 'Expand' : 'Minimize';
  minimizeButton.setAttribute('aria-expanded', String(!minimized));
});

clearHistoryButton.addEventListener('click', () => {
  historyList.innerHTML = '';
});

function newQuestion() {
  const a = Math.floor(Math.random() * 31) + 1;
  const b = Math.floor(Math.random() * 29) + 1;
  const operations = ['+', '-', '*', '/'];
  const op = operations[Math.floor(Math.random() * operations.length)];
  const answer = op === '+' ? a + b : op === '-' ? a - b : op === '*' ? a * b : Number((a / b).toFixed(3));
  currentQuestion = { text: `${a} ${op} ${b}`, answer };
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
  if (Math.abs(userValue - currentQuestion.answer) < 0.001) {
    correctCount += 1;
    feedbackText.textContent = 'Correct! Great job.';
  } else {
    feedbackText.textContent = `Not quite. Correct answer: ${currentQuestion.answer}`;
  }
  updateScore();
}

checkAnswerButton.addEventListener('click', checkAnswer);
newQuestionButton.addEventListener('click', newQuestion);
answerInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    checkAnswer();
  }
});

updateCalculatorUi();
updateScore();
