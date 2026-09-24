
function copyContent(element) {
	const expandedDiv = element.parentElement;
	const text = expandedDiv.querySelector('.content').textContent;
	navigator.clipboard.writeText(text);
}


function initializeChatView() {
	const messages = document.querySelectorAll('.message');
	if (!messages.length) return;

	messages.forEach((message, i) => {
		const isLast = i === messages.length - 1;
		const selector = isLast ? '.tool' : '.prompt, .reasoning, .tool, .error, .response';

		message.querySelectorAll(selector).forEach(container => {
			const expandedDiv = container.children[0];
			const collapsedDiv = container.children[1];

			if (expandedDiv && collapsedDiv) {
				expandedDiv.style.display = 'none';
				collapsedDiv.style.display = 'block';
			}
		});
	});

	window.scrollTo(0, document.body.scrollHeight);
}














function toggleMessage(container) {
	if (window.getSelection().toString()) return;
	const expanded = container.children[0];
	const collapsed = container.children[1];
	const isExpanded = expanded.style.display !== 'none';
	expanded.style.display = isExpanded ? 'none' : 'block';
	collapsed.style.display = isExpanded ? 'block' : 'none';
}

const TOOLS_STORAGE_KEY = 'chatpad-enabled-tools';

function toggleTool(el) {
	const input = el.nextElementSibling;
	const enabled = el.classList.toggle('enabled');
	input.disabled = !enabled;
	saveEnabledTools();
}

function restoreEnabledTools() {
	let enabled;
	try {
		enabled = JSON.parse(localStorage.getItem(TOOLS_STORAGE_KEY)) || [];
	} catch (e) {
		enabled = [];
	}
	document.querySelectorAll('.tool-toggle').forEach(el => {
		const input = el.nextElementSibling;
		const on = enabled.includes(el.dataset.name);
		el.classList.toggle('enabled', on);
		input.disabled = !on;
	});
}

function saveEnabledTools() {
	const enabled = Array.from(document.querySelectorAll('.tool-toggle.enabled')).map(el => el.dataset.name);
	localStorage.setItem(TOOLS_STORAGE_KEY, JSON.stringify(enabled));
}

const REASONING_STORAGE_KEY = 'chatpad-reasoning-enabled';

function toggleReasoning(el) {
	const input = el.nextElementSibling;
	const enabled = el.classList.toggle('enabled');
	input.disabled = !enabled;
	saveReasoning();
}

function restoreReasoning() {
	const el = document.querySelector('.opt-reasoning .tool-toggle');
	if (!el) return;
	const input = el.nextElementSibling;
	const saved = localStorage.getItem(REASONING_STORAGE_KEY);
	const on = saved === null ? true : saved === 'true';
	el.classList.toggle('enabled', on);
	input.disabled = !on;
}

function saveReasoning() {
	const el = document.querySelector('.opt-reasoning .tool-toggle');
	if (!el) return;
	localStorage.setItem(REASONING_STORAGE_KEY, el.classList.contains('enabled'));
}

const MODEL_STORAGE_KEY = 'chatpad-selected-model';

function toggleModelList() {
	const list = document.getElementById('model-list');
	const collapsed = list.classList.toggle('collapsed');
	if (!collapsed) {
		document.querySelector('.tools-list').classList.add('collapsed');
	}
}

function toggleToolsList() {
	const list = document.querySelector('.tools-list');
	const collapsed = list.classList.toggle('collapsed');
	if (!collapsed) {
		document.getElementById('model-list').classList.add('collapsed');
	}
}

async function refreshModels() {
	await fetch('/api/refresh-models', { method: 'POST' });
	location.reload();
}

function selectModel(el) {
	document.querySelectorAll('#model-list .model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	document.getElementById('model-input').value = el.dataset.id;
	document.getElementById('model-header').textContent = el.dataset.id;
	document.getElementById('model-list').classList.add('collapsed');
	saveSelectedModel();
}

function restoreSelectedModel() {
	const saved = localStorage.getItem(MODEL_STORAGE_KEY);
	if (!saved) return;
	const el = document.querySelector(`#model-list .model-toggle[data-id="${CSS.escape(saved)}"]`);
	if (el) selectModel(el);
}

function saveSelectedModel() {
	localStorage.setItem(MODEL_STORAGE_KEY, document.getElementById('model-input').value);
}

const SYSTEM_MODEL_STORAGE_KEY = 'chatpad-system-model';

function toggleSystemModelList() {
	const collapsed = document.getElementById('system-model-list').classList.toggle('collapsed');
	document.getElementById('system-model-header').classList.toggle('hidden', !collapsed);
}

function selectSystemModel(el) {
	document.querySelectorAll('#system-model-list .model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	document.getElementById('system-model-header').textContent = el.dataset.id || 'none';
	document.getElementById('system-model-header').classList.remove('hidden');
	document.getElementById('system-model-list').classList.add('collapsed');
	localStorage.setItem(SYSTEM_MODEL_STORAGE_KEY, el.dataset.id);
}

function restoreSystemModel() {
	const saved = localStorage.getItem(SYSTEM_MODEL_STORAGE_KEY);
	if (!saved) return;
	const el = document.querySelector(`#system-model-list .model-toggle[data-id="${CSS.escape(saved)}"]`);
	if (el) selectSystemModel(el);
}

document.addEventListener('DOMContentLoaded', function() {
	restoreEnabledTools();
	restoreSelectedModel();
	restoreReasoning();
	restoreSystemModel();
	initLiveChat();
	initChatboxClearance();
});

function initChatboxClearance() {
	const bar = document.querySelector('.chatbox-bar');
	if (!bar) return;
	const update = () => { document.body.style.paddingBottom = bar.offsetHeight + 'px'; };
	update();
	new ResizeObserver(update).observe(bar);
}

async function renderMarkdown(text) {
	const response = await fetch('/api/markdown', { method: 'POST', body: new URLSearchParams({ text }) });
	return response.text();
}

function formatNowTime() {
	const d = new Date();
	return [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => String(n).padStart(2, '0')).join(':');
}

function short(text, n = 30) {
	text = text || '';
	return text.length > n ? text.slice(0, n) + '...' : text;
}

function buildBlock(className, expandedNode, collapsedText) {
	const div = document.createElement('div');
	div.className = className;
	div.onclick = function() { toggleMessage(div); };

	const expandedWrap = document.createElement('div');
	const expandedContent = document.createElement('div');
	expandedContent.className = 'content';
	expandedContent.appendChild(expandedNode);
	expandedWrap.appendChild(expandedContent);

	const collapsedWrap = document.createElement('div');
	collapsedWrap.style.display = 'none';
	const collapsedSpan = document.createElement('span');
	collapsedSpan.textContent = collapsedText;
	collapsedWrap.appendChild(collapsedSpan);

	div.appendChild(expandedWrap);
	div.appendChild(collapsedWrap);
	return div;
}

async function appendPromptBlock(turnDiv, record) {
	const time = formatNowTime();

	const div = document.createElement('div');
	div.className = 'prompt';
	div.onclick = function() { toggleMessage(div); };

	const expandedWrap = document.createElement('div');
	const expandedContent = document.createElement('div');
	expandedContent.className = 'content';
	const expandedTime = document.createElement('span');
	expandedTime.className = 'turn-time';
	expandedTime.textContent = time;
	expandedContent.appendChild(expandedTime);
	expandedContent.appendChild(document.createTextNode(' ' + record.content));
	expandedWrap.appendChild(expandedContent);

	const collapsedWrap = document.createElement('div');
	collapsedWrap.style.display = 'none';
	const collapsedTime = document.createElement('span');
	collapsedTime.className = 'turn-time';
	collapsedTime.textContent = time;
	const collapsedText = document.createElement('span');
	collapsedText.textContent = short(record.content);
	collapsedWrap.appendChild(collapsedTime);
	collapsedWrap.appendChild(collapsedText);

	div.appendChild(expandedWrap);
	div.appendChild(collapsedWrap);
	turnDiv.appendChild(div);

	if (record.model) {
		const info = document.createElement('div');
		info.className = 'info';
		const small = document.createElement('small');
		small.textContent = record.model;
		info.appendChild(small);
		turnDiv.appendChild(info);
	}
}

async function appendReasoningBlock(turnDiv, record) {
	const html = await renderMarkdown(record.content);
	const contentNode = document.createElement('div');
	contentNode.innerHTML = html;
	const div = buildBlock('reasoning', contentNode, short(contentNode.textContent));
	div.children[0].style.display = 'block';
	div.children[1].style.display = 'none';
	turnDiv.appendChild(div);
}

async function appendResponseBlock(turnDiv, record) {
	const html = await renderMarkdown(record.content);
	const contentNode = document.createElement('div');
	contentNode.innerHTML = html;
	const div = buildBlock('response', contentNode, short(contentNode.textContent));
	div.children[0].style.display = 'block';
	div.children[1].style.display = 'none';
	turnDiv.appendChild(div);
}

async function appendErrorBlock(turnDiv, record) {
	const contentNode = document.createElement('div');
	const p = document.createElement('p');
	p.textContent = record.error.message;
	contentNode.appendChild(p);
	if (record.error.code) {
		const small = document.createElement('small');
		small.textContent = 'Code: ' + record.error.code;
		contentNode.appendChild(small);
	}
	const div = buildBlock('error', contentNode, short(record.error.message));
	div.children[0].style.display = 'block';
	div.children[1].style.display = 'none';
	turnDiv.appendChild(div);
}

function appendToolCallBlock(turnDiv, record) {
	record.tool_calls.forEach(call => {
		const contentNode = document.createElement('div');
		const summary = document.createElement('div');
		summary.className = 'tool-summary';
		summary.textContent = `${call.function.name}(${call.function.arguments})`;
		const raw = document.createElement('div');
		raw.className = 'tool-raw';
		raw.textContent = `${call.function.name}(${call.function.arguments})`;
		contentNode.appendChild(summary);
		contentNode.appendChild(raw);

		const div = buildBlock('tool', contentNode, `${call.function.name}(${call.function.arguments})`.slice(0, 30));
		div.dataset.callId = call.id;
		div.children[0].style.display = 'none';
		div.children[1].style.display = 'block';
		turnDiv.appendChild(div);
	});
}

function appendToolResultBlock(turnDiv, record) {
	const div = turnDiv.querySelector(`.tool[data-call-id="${CSS.escape(record.tool_call_id)}"]`);
	if (!div) return;
	if (record.error) div.classList.add('error');
	const raw = document.createElement('div');
	raw.className = 'tool-raw';
	raw.textContent = record.content;
	div.children[0].querySelector('.content').appendChild(raw);
}

function ensureMessagesContainer() {
	let el = document.querySelector('.messages');
	if (el) return el;
	el = document.createElement('div');
	el.className = 'messages';
	const archiveControls = document.getElementById('archive-controls');
	if (archiveControls) archiveControls.before(el);
	else document.querySelector('main').appendChild(el);
	return el;
}

function buildArchiveForm(sessionId) {
	const container = document.getElementById('archive-controls');
	if (!container || container.querySelector('form')) return;
	const form = document.createElement('form');
	form.className = 'chatbox-clearance';
	form.action = `/api/${sessionId}/archive`;
	form.method = 'post';
	const button = document.createElement('button');
	button.type = 'submit';
	button.textContent = 'Archive';
	form.appendChild(button);
	container.appendChild(form);
}

function promoteToSession(sessionId) {
	liveSessionId = sessionId;
	history.pushState(null, '', `/chat/${sessionId}`);
	buildArchiveForm(sessionId);
	const table = document.getElementById('sessions-table');
	if (table) table.style.display = 'none';
}

async function handleBlock(turnDiv, record) {
	if (!liveSessionId) promoteToSession(record.session);
	if (record.type === 'prompt') await appendPromptBlock(turnDiv, record);
	else if (record.type === 'reasoning') await appendReasoningBlock(turnDiv, record);
	else if (record.type === 'response' && record.content) await appendResponseBlock(turnDiv, record);
	else if (record.type === 'error') await appendErrorBlock(turnDiv, record);
	else if (record.type === 'tool_call') appendToolCallBlock(turnDiv, record);
	else if (record.type === 'tool_result') appendToolResultBlock(turnDiv, record);
	window.scrollTo(0, document.body.scrollHeight);
}

let liveSessionId = null;

async function submitLiveChat(event) {
	event.preventDefault();
	const form = event.currentTarget;
	const formData = new FormData(form);
	const promptEl = document.getElementById('prompt');
	promptEl.value = '';
	const button = form.querySelector('button[type="submit"]');
	button.disabled = true;

	initializeChatView();
	const turnDiv = document.createElement('div');
	turnDiv.className = 'message';
	ensureMessagesContainer().appendChild(turnDiv);

	const url = liveSessionId ? `/api/${liveSessionId}/blocks` : '/api/blocks';
	try {
		const response = await fetch(url, { method: 'POST', body: formData });
		const reader = response.body.getReader();
		const decoder = new TextDecoder();
		let buffer = '';
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			const parts = buffer.split('\n\n');
			buffer = parts.pop();
			for (const part of parts) {
				if (!part.startsWith('data: ')) continue;
				const record = JSON.parse(part.slice(6));
				await handleBlock(turnDiv, record);
			}
		}
	} finally {
		button.disabled = false;
	}
}

function initLiveChat() {
	if (typeof SESSION_ID === 'undefined') return;
	liveSessionId = SESSION_ID || null;
	const form = document.getElementById('chat-form');
	if (!form) return;
	form.addEventListener('submit', submitLiveChat);
}
