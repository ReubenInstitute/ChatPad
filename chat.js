function copyBlock(button) {
	const content = button.parentElement.querySelector('.content');
	const clone = content.cloneNode(true);
	clone.querySelectorAll('.turn-time').forEach(el => el.remove());
	navigator.clipboard.writeText(clone.textContent.trim());
}

async function hideMessageTurn(button, sessionId, uuid) {
	const message = button.closest('.message');
	message.classList.toggle('message-hidden');
	await fetch(`/api/${sessionId}/hide/${uuid}`, { method: 'POST' });
}


function initializeChatView() {
	const messages = document.querySelectorAll('.message');
	if (!messages.length) return;

	messages.forEach((message, i) => {
		const isLast = i === messages.length - 1;
		const selector = isLast ? '.tool' : '.prompt, .reasoning, .tool, .error, .response';

		message.querySelectorAll(selector).forEach(container => {
			container.classList.add('collapsed');
		});
	});

	window.scrollTo(0, document.body.scrollHeight);
}














function toggleMessage(container) {
	if (window.getSelection().toString()) return;
	container.classList.toggle('collapsed');
}

const TOOLS_STORAGE_KEY = 'chatpad-enabled-tools';

// fetch_url was split into get_url and download_url
const LEGACY_TOOLS = { 'fetch_url': ['get_url', 'download_url'] };

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
	const current = Array.from(document.querySelectorAll('.tool-toggle')).map(el => el.dataset.name);
	const wanted = new Set();
	enabled.forEach(name => {
		if (current.includes(name)) wanted.add(name);
		(LEGACY_TOOLS[name] || []).forEach(newname => wanted.add(newname));
	});
	document.querySelectorAll('.tool-toggle').forEach(el => {
		const input = el.nextElementSibling;
		const on = wanted.has(el.dataset.name);
		el.classList.toggle('enabled', on);
		input.disabled = !on;
	});
	saveEnabledTools();
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
	const el = document.getElementById('reasoning-toggle');
	if (!el) return;
	const input = el.nextElementSibling;
	const saved = localStorage.getItem(REASONING_STORAGE_KEY);
	const on = saved === null ? true : saved === 'true';
	el.classList.toggle('enabled', on);
	input.disabled = !on;
}

function saveReasoning() {
	const el = document.getElementById('reasoning-toggle');
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

// Mirror the picked option's icon and name onto the collapsed menu header, so
// the closed menu shows which model is selected. Options carry their icon as a
// nested <img class="model-icon-small"> (absent for the "none" option); the
// header is an <img> + <span> pair so the icon can be swapped in and out.
function setHeaderModel(header, source) {
	const sourceIcon = source.querySelector('img.model-icon-small');
	const headerIcon = header.querySelector('img.model-icon-small');
	const nameEl = header.querySelector('span');
	if (headerIcon) {
		if (sourceIcon) {
			headerIcon.src = sourceIcon.src;
			headerIcon.hidden = false;
		} else {
			headerIcon.removeAttribute('src');
			headerIcon.hidden = true;
		}
	}
	if (nameEl) nameEl.textContent = source.dataset.name;
}

function selectModel(el) {
	document.querySelectorAll('#model-list .model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	document.getElementById('model-input').value = el.dataset.id;
	setHeaderModel(document.getElementById('model-header'), el);
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
	setHeaderModel(document.getElementById('system-model-header'), el);
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
	restoreMode();
	restoreSystemModel();
	initLiveChat();
	initChatboxClearance();
	initFollowStream();
	lucide.createIcons();
});

const MODE_STORAGE_KEY = 'chatpad-mode';

function setMode(el, mode) {
	el.dataset.mode = mode;
	el.classList.toggle('enabled', mode === 'manual');
	el.title = mode === 'manual' ? 'Manual: approve each tool call' : 'Auto: tools run without approval';
	document.getElementById('mode-input').value = mode;
}

function toggleMode(el) {
	setMode(el, el.dataset.mode === 'manual' ? 'auto' : 'manual');
	saveMode();
}

function restoreMode() {
	const el = document.getElementById('mode-toggle');
	if (!el) return;
	setMode(el, localStorage.getItem(MODE_STORAGE_KEY) || 'auto');
}

function saveMode() {
	const el = document.getElementById('mode-toggle');
	if (!el) return;
	localStorage.setItem(MODE_STORAGE_KEY, el.dataset.mode);
}

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

function iconify(root) {
	lucide.createIcons({ root });
}

function buildCopyIcon() {
	const span = document.createElement('span');
	span.className = 'copy-icon';
	span.title = 'Copy';
	span.innerHTML = '<i data-lucide="copy"></i>';
	iconify(span);
	span.onclick = function(e) { e.stopPropagation(); copyBlock(span); };
	return span;
}

function buildBlock(className, expandedNode) {
	const div = document.createElement('div');
	div.className = className;
	div.onclick = function() { toggleMessage(div); };

	const content = document.createElement('div');
	content.className = 'content';
	content.appendChild(expandedNode);
	div.appendChild(content);
	div.appendChild(buildCopyIcon());
	return div;
}

async function appendPromptBlock(turnDiv, record) {
	const time = formatNowTime();

	const div = document.createElement('div');
	div.className = 'prompt';
	div.onclick = function() { toggleMessage(div); };

	const content = document.createElement('div');
	content.className = 'content';
	const timeSpan = document.createElement('span');
	timeSpan.className = 'turn-time';
	timeSpan.textContent = time;
	content.appendChild(timeSpan);
	content.appendChild(document.createTextNode(' ' + record.content));
	div.appendChild(content);
	div.appendChild(buildCopyIcon());
	turnDiv.appendChild(div);

	ensureMessageActions(turnDiv, record.session, record.uuid);
}

function ensureMessageActions(turnDiv, sessionId, uuid) {
	let div = turnDiv.querySelector('.message-actions');
	if (!div) {
		div = document.createElement('div');
		div.className = 'message-actions';
		const hideIcon = document.createElement('span');
		hideIcon.className = 'hide-icon';
		hideIcon.title = 'Hide from history';
		hideIcon.innerHTML = '<i data-lucide="eye-off"></i>';
		hideIcon.onclick = function() { hideMessageTurn(hideIcon, sessionId, uuid); };
		div.appendChild(hideIcon);
		iconify(div);
	}
	turnDiv.appendChild(div);
	return div;
}

function ensureLiveBlock(turnDiv, liveState, target) {
	if (liveState[target]) return liveState[target];
	const className = target === 'reasoning' ? 'reasoning' : 'response';
	const contentNode = document.createElement('div');
	const div = buildBlock(className, contentNode);
	turnDiv.appendChild(div);
	const state = { div, content: div.querySelector('.content'), html: '' };
	liveState[target] = state;
	scrollIfAtBottom();
	return state;
}

// Follow the stream only while the reader is at the bottom, so scrolling up to
// read is never yanked back down by an incoming patch. The flag is driven by
// real scroll events rather than measured at paint time, so content growing
// cannot by itself push the reader out of the follow zone.
let followStream = true;

function initFollowStream() {
	const update = () => {
		followStream = document.body.scrollHeight - window.innerHeight - window.scrollY < 120;
	};
	window.addEventListener('scroll', update, { passive: true });
	update();
}

function scrollIfAtBottom() {
	if (followStream) window.scrollTo(0, document.body.scrollHeight);
}

function applyHtmlPatch(turnDiv, liveState, target, patchText) {
	const state = ensureLiveBlock(turnDiv, liveState, target);
	const dmp = new diff_match_patch();
	const patches = dmp.patch_fromText(patchText);
	const [newHtml] = dmp.patch_apply(patches, state.html);
	state.html = newHtml;
	state.content.innerHTML = newHtml;
	scrollIfAtBottom();
}

function discardLiveBlock(liveState, target) {
	const state = liveState && liveState[target];
	if (state) {
		state.div.remove();
		liveState[target] = null;
	}
}

function finalizeLiveBlock(liveState, target) {
	const state = liveState && liveState[target];
	if (state) {
		liveState[target] = null;
	}
}

async function appendReasoningBlock(turnDiv, record, liveState) {
	const html = await renderMarkdown(record.content);
	const live = liveState && liveState.reasoning;
	if (live) {
		live.content.innerHTML = html;
		liveState.reasoning = null;
		return;
	}
	const contentNode = document.createElement('div');
	contentNode.innerHTML = html;
	const div = buildBlock('reasoning', contentNode);
	turnDiv.appendChild(div);
}

async function appendResponseBlock(turnDiv, record, liveState) {
	const html = await renderMarkdown(record.content);
	const live = liveState && liveState.response;
	if (live) {
		live.content.innerHTML = html;
		liveState.response = null;
	} else {
		const contentNode = document.createElement('div');
		contentNode.innerHTML = html;
		const div = buildBlock('response', contentNode);
		turnDiv.appendChild(div);
	}

	// Model + usage lines, grouped in one wrapper so they stack with no gap
	if (record.model || record.usage) {
		const meta = document.createElement('div');
		meta.className = 'turn-meta';
		if (record.model) {
			const info = document.createElement('div');
			info.className = 'info';
			if (record.icon) {
				const img = document.createElement('img');
				img.className = 'model-icon';
				img.src = record.icon;
				img.alt = '';
				info.appendChild(img);
			}
			const small = document.createElement('small');
			small.textContent = record.model_name || record.model;
			info.appendChild(small);
			meta.appendChild(info);
		}
		if (record.usage) {
			const usageDiv = document.createElement('div');
			usageDiv.className = 'usage-info';
			const small = document.createElement('small');
			let parts = [];
			if (record.usage.prompt_tokens) parts.push('Prompt: ' + record.usage.prompt_tokens);
			if (record.usage.completion_tokens) parts.push('Completion: ' + record.usage.completion_tokens);
			if (record.usage.total_tokens) parts.push('Total: ' + record.usage.total_tokens);
			if (record.usage.cost !== undefined && record.usage.cost !== null) parts.push('Cost: $' + record.usage.cost.toFixed(6));
			small.textContent = parts.join(' | ');
			usageDiv.appendChild(small);
			meta.appendChild(usageDiv);
		}
		turnDiv.appendChild(meta);
	}
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
	const div = buildBlock('error', contentNode);
	turnDiv.appendChild(div);
}

function appendToolCallBlock(turnDiv, record, liveState) {
	finalizeLiveBlock(liveState, 'response');
	const labels = record.labels || {};
	record.tool_calls.forEach(call => {
		const label = labels[call.id] || `${call.function.name}(${call.function.arguments})`;

		if (NO_CONTENT_TOOLS.includes(call.function.name)) {
			const div = document.createElement('div');
			div.className = 'tool tool-static';
			const wrap = document.createElement('div');
			const span = document.createElement('span');
			span.textContent = label;
			wrap.appendChild(span);
			div.appendChild(wrap);
			div.dataset.callId = call.id;
			turnDiv.appendChild(div);
			return;
		}

		const contentNode = document.createElement('div');
		const summary = document.createElement('div');
		summary.className = 'tool-summary';
		summary.textContent = label;
		contentNode.appendChild(summary);

		const div = buildBlock('tool', contentNode);
		div.dataset.callId = call.id;
		div.classList.add('collapsed');
		turnDiv.appendChild(div);
	});
}

function appendToolResultBlock(turnDiv, record) {
	const div = turnDiv.querySelector(`.tool[data-call-id="${CSS.escape(record.tool_call_id)}"]`);
	if (!div) return;
	if (record.error) div.classList.add('error');
	const content = div.querySelector('.content');
	if (!content) {
		// no-content tool: the block has no expansion, so an error goes on its line
		if (record.error) {
			const line = div.children[0].querySelector('span');
			if (line) line.textContent += ' ' + record.error.message;
		}
		return;
	}
	if (!record.content) return;   // blanked result: nothing to add
	const raw = document.createElement('div');
	raw.className = 'tool-raw';
	raw.textContent = record.content;
	content.appendChild(raw);
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
	if (!container) return;
	if (!container.querySelector('form')) {
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
	if (!container.querySelector('.session-raw-link')) {
		const rawLink = document.createElement('a');
		rawLink.className = 'session-raw-link';
		rawLink.href = `/api/${sessionId}/raw`;
		rawLink.textContent = 'raw';
		container.appendChild(rawLink);
	}
}

function promoteToSession(sessionId) {
	liveSessionId = sessionId;
	history.pushState(null, '', `/chat/${sessionId}`);
	buildArchiveForm(sessionId);
	const table = document.getElementById('sessions-table');
	if (table) table.style.display = 'none';
}

async function handleBlock(turnDiv, record, liveState) {
	if (!liveSessionId) promoteToSession(record.session);
	if (record.type === 'prompt') await appendPromptBlock(turnDiv, record);
	else if (record.type === 'html_patch') applyHtmlPatch(turnDiv, liveState, record.target, record.patch);
	else if (record.type === 'discard_block') discardLiveBlock(liveState, record.target);
	else if (record.type === 'finalize_block') finalizeLiveBlock(liveState, record.target);
	else if (record.type === 'reasoning') await appendReasoningBlock(turnDiv, record, liveState);
	else if (record.type === 'response' && record.content) await appendResponseBlock(turnDiv, record, liveState);
	else if (record.type === 'error') await appendErrorBlock(turnDiv, record);
	else if (record.type === 'tool_call') appendToolCallBlock(turnDiv, record, liveState);
	else if (record.type === 'tool_result') appendToolResultBlock(turnDiv, record);
	else if (record.type === 'await_approval') appendApprovalControls(turnDiv);
	else if (record.type === 'tool_stopped') appendToolStoppedBlock(turnDiv);
	const actions = turnDiv.querySelector('.message-actions');
	if (actions) turnDiv.appendChild(actions);
	scrollIfAtBottom();
}

function appendApprovalControls(turnDiv) {
	const div = document.createElement('div');
	div.className = 'approval-controls';
	['approve', 'deny', 'stop'].forEach(action => {
		const button = document.createElement('button');
		button.type = 'button';
		button.dataset.action = action;
		button.textContent = action[0].toUpperCase() + action.slice(1);
		button.onclick = () => resumeToolCalls(action, button);
		div.appendChild(button);
	});
	turnDiv.appendChild(div);
}

function appendToolStoppedBlock(turnDiv) {
	const div = document.createElement('div');
	div.className = 'tool-stopped';
	div.textContent = 'Stopped';
	turnDiv.appendChild(div);
}

function lastFormValues() {
	const form = document.getElementById('chat-form');
	return new FormData(form);
}

async function consumeBlockStream(response, turnDiv, liveState) {
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
			await handleBlock(turnDiv, record, liveState);
		}
	}
}

async function resumeToolCalls(action, button) {
	const controlsDiv = button.closest('.approval-controls');
	const turnDiv = controlsDiv.closest('.message');
	controlsDiv.remove();

	const formValues = lastFormValues();
	const resumeData = new FormData();
	resumeData.set('action', action);
	resumeData.set('model', formValues.get('model'));
	if (formValues.get('reasoning') !== null) resumeData.set('reasoning', '1');
	formValues.getAll('tools').forEach(t => resumeData.append('tools', t));
	resumeData.set('mode', formValues.get('mode') || 'auto');

	if (!liveSessionId) liveSessionId = SESSION_ID;
	const liveState = { reasoning: null, response: null };
	const response = await fetch(`/api/${liveSessionId}/resume-blocks`, { method: 'POST', body: resumeData });
	await consumeBlockStream(response, turnDiv, liveState);
}

let liveSessionId = null;

async function submitLiveChat(event) {
	event.preventDefault();
	const form = event.currentTarget;
	const formData = new FormData(form);
	const promptEl = document.getElementById('prompt');
	promptEl.value = '';
	const button = form.querySelector('button[type="submit"]');
	if (button) button.disabled = true;

	initializeChatView();
	const turnDiv = document.createElement('div');
	turnDiv.className = 'message';
	ensureMessagesContainer().appendChild(turnDiv);
	const liveState = { reasoning: null, response: null };

	const url = liveSessionId ? `/api/${liveSessionId}/blocks` : '/api/blocks';
	try {
		const response = await fetch(url, { method: 'POST', body: formData });
		await consumeBlockStream(response, turnDiv, liveState);
	} finally {
		if (button) button.disabled = false;
	}
}

function initLiveChat() {
	if (typeof SESSION_ID === 'undefined') return;
	liveSessionId = SESSION_ID || null;
	const form = document.getElementById('chat-form');
	if (!form) return;
	form.addEventListener('submit', submitLiveChat);

	const pendingControls = document.getElementById('approval-controls');
	if (pendingControls) {
		pendingControls.querySelectorAll('button').forEach(btn => {
			btn.onclick = () => resumeToolCalls(btn.dataset.action, btn);
		});
	}
}
