const canvas = document.getElementById('drawing-canvas');
const ctx = canvas.getContext('2d');

const toolSelect = document.getElementById('tool-select');
const colorPicker = document.getElementById('color-picker');
const sizePicker = document.getElementById('size-picker');
const fillToggle = document.getElementById('fill-toggle');
const undoButton = document.getElementById('undo-button');
const redoButton = document.getElementById('redo-button');
const clearButton = document.getElementById('clear-button');
const downloadButton = document.getElementById('download-button');

let drawing = false;
let fillShapes = false;
let startX = 0;
let startY = 0;
let lastX = 0;
let lastY = 0;
let snapshot = null;

const undoStack = [];
const redoStack = [];
const HISTORY_LIMIT = 50;

function resizeCanvas() {
  const { width, height } = canvas.getBoundingClientRect();
  const imageData = ctx.getImageData(0, 0, canvas.width || 1, canvas.height || 1);

  canvas.width = Math.max(300, Math.floor(width));
  canvas.height = Math.max(240, Math.floor(height));

  fillWhiteBackground();

  if (imageData.width > 1 || imageData.height > 1) {
    ctx.putImageData(imageData, 0, 0);
  }
}

function fillWhiteBackground() {
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function getPos(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  };
}

function saveState(stack = undoStack, clearRedo = true) {
  if (stack.length >= HISTORY_LIMIT) {
    stack.shift();
  }
  stack.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
  if (clearRedo) {
    redoStack.length = 0;
  }
}

function restoreState(fromStack, toStack) {
  if (!fromStack.length) {
    return;
  }
  toStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
  const previous = fromStack.pop();
  ctx.putImageData(previous, 0, 0);
}

function applyStrokeStyle() {
  ctx.lineWidth = Number(sizePicker.value);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = toolSelect.value === 'eraser' ? '#ffffff' : colorPicker.value;
}

function drawFreehand(x, y) {
  applyStrokeStyle();
  ctx.beginPath();
  ctx.moveTo(lastX, lastY);
  ctx.lineTo(x, y);
  ctx.stroke();
  lastX = x;
  lastY = y;
}

function drawShapePreview(x, y) {
  if (!snapshot) {
    return;
  }

  ctx.putImageData(snapshot, 0, 0);
  applyStrokeStyle();
  const width = x - startX;
  const height = y - startY;

  if (toolSelect.value === 'line') {
    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(x, y);
    ctx.stroke();
    return;
  }

  if (toolSelect.value === 'rectangle') {
    if (fillShapes) {
      ctx.fillStyle = colorPicker.value;
      ctx.fillRect(startX, startY, width, height);
    }
    ctx.strokeRect(startX, startY, width, height);
    return;
  }

  if (toolSelect.value === 'circle') {
    const radius = Math.hypot(width, height);
    ctx.beginPath();
    ctx.arc(startX, startY, radius, 0, Math.PI * 2);
    if (fillShapes) {
      ctx.fillStyle = colorPicker.value;
      ctx.fill();
    }
    ctx.stroke();
  }
}

function onPointerDown(event) {
  const pos = getPos(event);
  drawing = true;
  startX = pos.x;
  startY = pos.y;
  lastX = pos.x;
  lastY = pos.y;

  saveState();

  if (toolSelect.value === 'brush' || toolSelect.value === 'eraser') {
    drawFreehand(pos.x, pos.y);
  } else {
    snapshot = ctx.getImageData(0, 0, canvas.width, canvas.height);
  }
}

function onPointerMove(event) {
  if (!drawing) {
    return;
  }
  const pos = getPos(event);

  if (toolSelect.value === 'brush' || toolSelect.value === 'eraser') {
    drawFreehand(pos.x, pos.y);
  } else {
    drawShapePreview(pos.x, pos.y);
  }
}

function onPointerUp(event) {
  if (!drawing) {
    return;
  }
  onPointerMove(event);
  drawing = false;
  snapshot = null;
}

function clearCanvas() {
  saveState();
  fillWhiteBackground();
}

function downloadImage() {
  const link = document.createElement('a');
  link.download = 'drawing.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
}

fillToggle.addEventListener('click', () => {
  fillShapes = !fillShapes;
  fillToggle.setAttribute('aria-pressed', String(fillShapes));
});

undoButton.addEventListener('click', () => restoreState(undoStack, redoStack));
redoButton.addEventListener('click', () => restoreState(redoStack, undoStack));
clearButton.addEventListener('click', clearCanvas);
downloadButton.addEventListener('click', downloadImage);

canvas.addEventListener('pointerdown', onPointerDown);
canvas.addEventListener('pointermove', onPointerMove);
canvas.addEventListener('pointerup', onPointerUp);
canvas.addEventListener('pointerleave', onPointerUp);
window.addEventListener('resize', resizeCanvas);

resizeCanvas();
saveState(undoStack, false);
