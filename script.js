const calculatorPanel = document.getElementById('calculator-panel');
const panelSize = document.getElementById('panel-size');
const minimizeButton = document.getElementById('minimize-button');
const calcDisplay = document.getElementById('calc-display');
const calcGrid = document.getElementById('calc-grid');
const historyList = document.getElementById('history-list');
const clearHistoryButton = document.getElementById('clear-history');

const questionText = document.getElementById('question-text');
const answerInput = document.getElementById('answer-input');
const checkAnswerButton = document.getElementById('check-answer');
const newQuestionButton = document.getElementById('new-question');
const feedbackText = document.getElementById('feedback-text');
const scoreText = document.getElementById('score-text');

let currentExpression = '0';
let lastAnswer = 0;
let currentQuestion = null;
let correctCount = 0;
let attemptCount = 0;

function updateDisplay() {
  calcDisplay.value = currentExpression;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return 'Error';
  }
  const rounded = Number(value.toFixed(10));
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

function appendHistory(entry) {
  const item = document.createElement('li');
  item.textContent = entry;
  historyList.prepend(item);
}

function safeEval(expression) {
  const cleaned = expression
    .replace(/pi/g, 'Math.PI')
    .replace(/\be\b/g, 'Math.E')
    .replace(/sin\(/g, 'Math.sin(')
    .replace(/cos\(/g, 'Math.cos(')
    .replace(/tan\(/g, 'Math.tan(')
    .replace(/sqrt\(/g, 'Math.sqrt(')
    .replace(/\^/g, '**');

  if (!/^[0-9+\-*/().,\s*MathPIEsincotaqr\*]*$/.test(cleaned)) {
    throw new Error('Unsafe expression');
  }

  // eslint-disable-next-line no-new-func
  const result = Function(`return (${cleaned})`)();
  if (!Number.isFinite(result)) {
    throw new Error('Math error');
  }
  return result;
}

function evaluateExpression() {
  try {
    const input = currentExpression;
    const result = safeEval(input);
    const formatted = formatNumber(result);
    appendHistory(`${input} = ${formatted}`);
    currentExpression = formatted;
    lastAnswer = result;
    updateDisplay();
  } catch {
    appendHistory(`${currentExpression} = Error`);
    currentExpression = 'Error';
    updateDisplay();
  }
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

function insertValue(value) {
  if (currentExpression === '0' || currentExpression === 'Error') {
    currentExpression = value;
  } else {
    currentExpression += value;
  }
  updateDisplay();
}

function newQuestion() {
  const a = Math.floor(Math.random() * 21) + 1;
  const b = Math.floor(Math.random() * 19) + 1;
  const operatorPool = ['+', '-', '*', '/'];
  const operator = operatorPool[Math.floor(Math.random() * operatorPool.length)];

  let answer;
  if (operator === '+') answer = a + b;
  if (operator === '-') answer = a - b;
  if (operator === '*') answer = a * b;
  if (operator === '/') answer = Number((a / b).toFixed(2));

  currentQuestion = {
    text: `${a} ${operator} ${b}`,
    answer
  };

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
  const isCorrect = Math.abs(userValue - currentQuestion.answer) < 0.01;

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

calcGrid.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) {
    return;
  }

  const { action, value } = button.dataset;

  if (action === 'clear') {
    clearDisplay();
    return;
  }
  if (action === 'delete') {
    deleteLastChar();
    return;
  }
  if (action === 'evaluate') {
    evaluateExpression();
    return;
  }
  if (action === 'ans') {
    insertValue(formatNumber(lastAnswer));
    return;
  }

  if (value) {
    insertValue(value);
  }
});

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
updateScore();
