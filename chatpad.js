class Turn {
	constructor(json, message) {
		this.uuid = json.uuid
		this.message = message
		this.hidden = json.hidden
		this.error = json.error
	}
}

class MessageTurn extends Turn {
	constructor(json, message) {
		super(json, message)
		this.model = json.model
		this.think = json.think
		this.prompt = json.prompt
		this.reasoning = json.reasoning
		this.response = json.response
		this.raw = json.raw
	}
}

class ToolTurn extends Turn {
	constructor(json, message) {
		super(json, message)
		this.tool = json.tool
		this.arguments = json.arguments
		this.result = json.result
		this.call_id = json.call_id
	}
}

class Message {
	constructor(json, session) {
		this.uuid = json.uuid
		this.session = session
		this.hidden = json.hidden
		this.input_tokens = json.input_tokens
		this.output_tokens = json.output_tokens
		this.turns = json.turns.map(t => "tool" in t ? new ToolTurn(t, this) : new MessageTurn(t, this))
	}
}

class Settings {
	constructor(json, session) {
		this.session = session
		this.model = json.model
		this.system_model = json.system_model
		this.tools = json.tools
		this.mode = json.mode
		this.think = json.think
		this.max_steps = json.max_steps
	}

	async save() {
		for (const key of ['model', 'system_model', 'tools', 'mode', 'think', 'max_steps']) {
			const value = this[key]
			if (value === null || value === undefined) continue
			await fetch(`/api/sessions/${this.session.uuid}/settings/${key}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ value }),
			})
		}
	}
}

class Session {
	constructor(json) {
		this.uuid = json.uuid
		this.archived = json.archived
		this.status = json.status
		this.settings = new Settings(json.settings, this)
		this.messages = json.messages.map(m => new Message(m, this))
	}
}

class SessionView {
	constructor(container, session) {
		this.container = container
		this.session = session
		this.message_views = []
	}

	draw() {
		this.session.messages.forEach(message => {
			const container = document.createElement('div')
			container.className = 'message'
			this.container.appendChild(container)
			const view = new MessageView(container, this, message)
			this.message_views.push(view)
			view.draw()
		})
	}

	update() {
		if (this.session.messages.length > this.message_views.length) {
			const message = this.session.messages[this.session.messages.length - 1]
			const container = document.createElement('div')
			container.className = 'message'
			this.container.appendChild(container)
			const view = new MessageView(container, this, message)
			this.message_views.push(view)
			view.draw()
			return
		}
		if (this.message_views.length === 0) return
		this.message_views[this.message_views.length - 1].update()
	}
}

class MessageView {
	constructor(container, session_view, message) {
		this.container = container
		this.session_view = session_view
		this.message = message
		this.turn_views = []
	}

	directChild(className) {
		return Array.from(this.container.children).find(c => c.classList.contains(className))
	}

	insertDirectChild(el) {
		const action = this.directChild('action')
		if (action) this.container.insertBefore(el, action)
		else this.container.appendChild(el)
	}

	draw() {
		this.message.turns.forEach(turn => this.drawTurn(turn))
		this.update()
	}

	drawTurn(turn) {
		const container = document.createElement('div')
		this.insertDirectChild(container)
		const view = turn instanceof ToolTurn
			? new ToolTurnView(container, this, turn)
			: new TurnView(container, this, turn)
		this.turn_views.push(view)
		view.draw()
	}

	update() {
		if (this.message.turns.length > this.turn_views.length) {
			this.drawTurn(this.message.turns[this.message.turns.length - 1])
		} else if (this.turn_views.length > 0) {
			this.turn_views[this.turn_views.length - 1].update()
		}
		this.updateInfo()
		this.drawHideAction()
	}

	updateInfo() {
		const turn = this.message.turns[this.message.turns.length - 1]
		if (!(turn instanceof MessageTurn) || !turn.model) return

		let model = this.directChild('info-model')
		if (!model) {
			model = document.createElement('div')
			model.className = 'info info-model'
			this.insertDirectChild(model)
		}
		model.innerHTML = ''
		if (turn.icon) {
			const img = document.createElement('img')
			img.src = turn.icon
			img.alt = ''
			model.appendChild(img)
		}
		const small = document.createElement('small')
		small.textContent = turn.model_name || turn.model
		model.appendChild(small)

		if (!turn.usage) return
		let usage = this.directChild('info-usage')
		if (!usage) {
			usage = document.createElement('div')
			usage.className = 'info info-usage'
			this.insertDirectChild(usage)
		}
		const parts = []
		if (turn.usage.prompt_tokens) parts.push('Input: ' + turn.usage.prompt_tokens)
		if (turn.usage.completion_tokens) parts.push('Output: ' + turn.usage.completion_tokens)
		if (turn.context_length) {
			let max = 'Max: ' + formatNumber(turn.context_length)
			if (turn.usage.prompt_tokens) max += ' (' + (turn.usage.prompt_tokens / turn.context_length * 100).toFixed(1) + '%)'
			parts.push(max)
		}
		usage.innerHTML = ''
		const small2 = document.createElement('small')
		small2.textContent = parts.join(' | ')
		usage.appendChild(small2)
	}

	drawHideAction() {
		if (this.directChild('action')) return
		const action = document.createElement('span')
		action.className = 'action'
		action.title = 'Hide from history'
		action.innerHTML = '<i data-lucide="eye-off"></i>'
		action.onclick = () => hideMessageTurn(action, this.message.uuid)
		this.container.appendChild(action)
		iconify(this.container)
	}
}

class TurnView {
	constructor(container, message_view, turn) {
		this.container = container
		this.message_view = message_view
		this.turn = turn
	}

	draw() {
		this.update()
	}

	update() {
		if (this.turn.prompt) this.updatePrompt(this.turn.prompt)
		if (this.turn.reasoning) this.updateBlock('reasoning', this.turn.reasoning)
		if (this.turn.response) this.updateBlock('response', this.turn.response)
		if (this.turn.error) this.updateError(this.turn.error)
	}

	updatePrompt(text) {
		let div = this.container.querySelector('.prompt')
		if (!div) div = this.createBlock('prompt')
		div.querySelector('.content').textContent = text
	}

	updateBlock(className, html) {
		let div = this.container.querySelector('.' + className)
		if (!div) div = this.createBlock(className)
		div.querySelector('.content').innerHTML = html
	}

	createBlock(className) {
		const div = document.createElement('div')
		div.className = className
		div.onclick = () => toggleMessage(div)

		const content = document.createElement('div')
		content.className = 'content'
		div.appendChild(content)

		const action = document.createElement('span')
		action.className = 'action'
		action.title = 'Copy'
		action.innerHTML = '<i data-lucide="copy"></i>'
		action.onclick = (e) => { e.stopPropagation(); copyBlock(action) }
		div.appendChild(action)

		this.container.appendChild(div)
		iconify(div)
		return div
	}

	updateError(error) {
		let div = this.container.querySelector('.error')
		if (!div) div = this.createBlock('error')
		const content = div.querySelector('.content')
		content.innerHTML = ''
		const p = document.createElement('p')
		p.textContent = error.message
		content.appendChild(p)
		if (error.code) {
			const small = document.createElement('small')
			small.textContent = 'Code: ' + error.code
			content.appendChild(small)
		}
	}
}

class ToolTurnView {
	constructor(container, message_view, turn) {
		this.container = container
		this.message_view = message_view
		this.turn = turn
	}

	draw() {
		this.container.className = 'tool'
		this.container.onclick = () => toggleMessage(this.container)

		const content = document.createElement('div')
		content.className = 'content'
		this.container.appendChild(content)

		const action = document.createElement('span')
		action.className = 'action'
		action.title = 'Copy'
		action.innerHTML = '<i data-lucide="copy"></i>'
		action.onclick = (e) => { e.stopPropagation(); copyBlock(action) }
		this.container.appendChild(action)
		iconify(this.container)

		this.update()
	}

	update() {
		this.container.classList.toggle('error', !!(this.turn.result && this.turn.result.error))
		const content = this.container.querySelector('.content')
		content.innerHTML = ''
		const summary = document.createElement('div')
		summary.textContent = this.turn.tool
		content.appendChild(summary)
		if (this.turn.result && this.turn.result.content) {
			const result = document.createElement('div')
			result.textContent = this.turn.result.content
			content.appendChild(result)
		}
	}
}

function copyBlock(button) {
	const content = button.parentElement.querySelector('.content');
	const clone = content.cloneNode(true);
	clone.querySelectorAll('.turn-time').forEach(el => el.remove());
	navigator.clipboard.writeText(clone.textContent.trim());
}

async function hideMessageTurn(button, uuid) {
	const message = button.closest('.message');
	message.classList.toggle('message-hidden');
	await fetch(`/api/sessions/${session.uuid}/messages/${uuid}/hide`, { method: 'POST' });
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

// fetch_url was split into get_url and download_url
const LEGACY_TOOLS = { 'fetch_url': ['get_url', 'download_url'] };

function toggleTool(el) {
	const input = el.nextElementSibling;
	const enabled = el.classList.toggle('enabled');
	input.disabled = !enabled;
	saveEnabledTools();
}

function restoreEnabledTools() {
	const enabled = session.settings.tools || [];
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
}

function saveEnabledTools() {
	session.settings.tools = Array.from(document.querySelectorAll('.tool-toggle.enabled')).map(el => el.dataset.name);
	session.settings.save();
}

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
	const on = session.settings.think == null ? true : session.settings.think;
	el.classList.toggle('enabled', on);
	input.disabled = !on;
}

function saveReasoning() {
	const el = document.getElementById('reasoning-toggle');
	if (!el) return;
	session.settings.think = el.classList.contains('enabled');
	session.settings.save();
}

function toggleModelList() {
	const list = document.getElementById('model-menu');
	const hidden = list.classList.toggle('hidden');
	if (!hidden) {
		document.getElementById('tools-menu').classList.add('hidden');
	}
}

function toggleToolsList() {
	const list = document.getElementById('tools-menu');
	const hidden = list.classList.toggle('hidden');
	if (!hidden) {
		document.getElementById('model-menu').classList.add('hidden');
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
	document.querySelectorAll('#model-menu .model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	document.querySelector('[name="model"]').value = el.dataset.id;
	setHeaderModel(document.getElementById('model-link'), el);
	document.getElementById('model-menu').classList.add('hidden');
	saveSelectedModel();
}

function restoreSelectedModel() {
	const saved = session.settings.model;
	if (!saved) return;
	const el = document.querySelector(`#model-menu .model-toggle[data-id="${CSS.escape(saved)}"]`);
	if (el) selectModel(el);
}

function saveSelectedModel() {
	session.settings.model = document.querySelector('[name="model"]').value;
	session.settings.save();
}

function toggleSystemModelList() {
	const hidden = document.getElementById('system-model-menu').classList.toggle('hidden');
	document.getElementById('system-model-link').classList.toggle('hidden', !hidden);
}

function selectSystemModel(el) {
	document.querySelectorAll('#system-model-menu .model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	setHeaderModel(document.getElementById('system-model-link'), el);
	document.getElementById('system-model-link').classList.remove('hidden');
	document.getElementById('system-model-menu').classList.add('hidden');
	session.settings.system_model = el.dataset.id;
	session.settings.save();
}

function restoreSystemModel() {
	const saved = session.settings.system_model;
	if (!saved) return;
	const el = document.querySelector(`#system-model-menu .model-toggle[data-id="${CSS.escape(saved)}"]`);
	if (el) selectSystemModel(el);
}

document.addEventListener('DOMContentLoaded', async function() {
	await init();
	restoreEnabledTools();
	restoreSelectedModel();
	restoreReasoning();
	restoreMode();
	restoreSystemModel();
	initChatboxClearance();
	initFollowStream();
	lucide.createIcons();
});

function setMode(el, mode) {
	el.dataset.mode = mode;
	el.classList.toggle('enabled', mode === 'manual');
	el.title = mode === 'manual' ? 'Manual: approve each tool call' : 'Auto: tools run without approval';
	document.querySelector('[name="mode"]').value = mode;
}

function toggleMode(el) {
	setMode(el, el.dataset.mode === 'manual' ? 'auto' : 'manual');
	saveMode();
}

function saveMode() {
	session.settings.mode = document.querySelector('[name="mode"]').value;
	session.settings.save();
}

function restoreMode() {
	const el = document.getElementById('mode-toggle');
	if (!el) return;
	setMode(el, session.settings.mode || 'auto');
}

function initChatboxClearance() {
	const bar = document.querySelector('.chatbox-bar');
	if (!bar) return;
	const update = () => { document.body.style.paddingBottom = bar.offsetHeight + 'px'; };
	update();
	new ResizeObserver(update).observe(bar);
}

function iconify(root) {
	lucide.createIcons({ root });
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

function ensureMessagesContainer() {
	let el = document.querySelector('.session');
	if (el) return el;
	el = document.createElement('div');
	el.className = 'session';
	const archiveControls = document.getElementById('archive-controls');
	if (archiveControls) archiveControls.before(el);
	else document.querySelector('main').appendChild(el);
	return el;
}

function buildArchiveForm() {
	const container = document.getElementById('archive-controls');
	if (!container) return;
	if (!container.querySelector('form')) {
		const form = document.createElement('form');
		form.className = 'chatbox-clearance';
		form.action = `/api/sessions/${session.uuid}/archive`;
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
		rawLink.href = `/api/sessions/${session.uuid}/raw`;
		rawLink.textContent = 'raw';
		container.appendChild(rawLink);
	}
}

function promoteToSession(sessionId) {
	session.uuid = sessionId;
	history.pushState(null, '', `/chat/${sessionId}`);
	buildArchiveForm();
	const table = document.getElementById('sessions-table');
	if (table) table.style.display = 'none';
}

let session = null;
let liveSessionView = null;

function updateSessionStatus(status) {
	session.status = status;
	const button = document.querySelector('#chat-form .action[title="Send"]');
	if (button) button.style.pointerEvents = status === 'idle' ? '' : 'none';
	if (status === 'awaiting') showApprovalControls();
	else removeApprovalControls();
}

function startLiveTurn(record) {
	initializeChatView();
	if (!session.uuid) promoteToSession(record.session);
	session.messages.push(new Message({ uuid: record.uuid, hidden: false, turns: [] }, session));
	liveSessionView.update();
}

function currentMessage() {
	return session.messages[session.messages.length - 1];
}

function currentTurn() {
	return currentMessage().turns[currentMessage().turns.length - 1];
}

function applyPatch(turn, target, patchText) {
	const dmp = new diff_match_patch();
	const patches = dmp.patch_fromText(patchText);
	const [newHtml] = dmp.patch_apply(patches, turn[target] || '');
	turn[target] = newHtml;
}

function toolLabel(record, call) {
	const labels = record.labels || {};
	return labels[call.id] || `${call.function.name}(${call.function.arguments})`;
}

async function renderMarkdown(text) {
	const response = await fetch('/api/markdown', { method: 'POST', body: new URLSearchParams({ text }) });
	return response.text();
}

async function handleStreamRecord(record) {
	if (record.type === 'status') {
		updateSessionStatus(record.status);
		return;
	}
	if (record.type === 'prompt') {
		startLiveTurn(record);
		currentMessage().turns.push(new MessageTurn({ prompt: record.content }, currentMessage()));
	} else if (!session || !session.messages.length) {
		return;
	} else if (record.type === 'html_patch') {
		applyPatch(currentTurn(), record.target, record.patch);
	} else if (record.type === 'reasoning') {
		currentTurn().reasoning = await renderMarkdown(record.content);
	} else if (record.type === 'response') {
		if (record.content) currentTurn().response = await renderMarkdown(record.content);
		if (record.model) currentTurn().model = record.model;
		if (record.model_name) currentTurn().model_name = record.model_name;
		if (record.icon) currentTurn().icon = record.icon;
		if (record.usage) currentTurn().usage = record.usage;
		if (record.context_length) currentTurn().context_length = record.context_length;
	} else if (record.type === 'error') {
		currentTurn().error = record.error;
	} else if (record.type === 'tool_call') {
		record.tool_calls.forEach(call => {
			currentMessage().turns.push(new ToolTurn({
				tool: toolLabel(record, call),
				arguments: call.function.arguments,
				result: null,
				call_id: call.id,
			}, currentMessage()));
		});
	} else if (record.type === 'tool_result') {
		const turn = currentMessage().turns.find(t => t instanceof ToolTurn && t.call_id === record.tool_call_id);
		if (turn) turn.result = { content: record.content, error: record.error };
	} else if (record.type === 'await_approval') {
		updateSessionStatus('awaiting');
	}
	liveSessionView.update();
	scrollIfAtBottom();
}

function showApprovalControls() {
	removeApprovalControls();
	const div = document.createElement('div');
	div.className = 'tool-approval';
	['approve', 'deny', 'stop'].forEach(action => {
		const button = document.createElement('button');
		button.type = 'button';
		button.dataset.action = action;
		button.textContent = action[0].toUpperCase() + action.slice(1);
		button.onclick = () => resumeToolCalls(action);
		div.appendChild(button);
	});
	ensureMessagesContainer().appendChild(div);
}

function removeApprovalControls() {
	const el = document.querySelector('.tool-approval');
	if (el) el.remove();
}

async function resumeToolCalls(action) {
	updateSessionStatus('busy');
	await fetch(`/api/sessions/${session.uuid}/resume`, { method: 'POST', body: new URLSearchParams({ action }) });
}

async function openLiveStream() {
	const response = await fetch(`/api/sessions/${session.uuid}/stream`);
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
			await handleStreamRecord(JSON.parse(part.slice(6)));
		}
	}
}

async function submitLiveChat(event) {
	event.preventDefault();
	const form = event.currentTarget;
	const formData = new FormData(form);
	const promptEl = form.querySelector('textarea[name="prompt"]');
	promptEl.value = '';

	const url = session.uuid ? `/api/sessions/${session.uuid}/message` : '/api/message';
	const response = await fetch(url, { method: 'POST', body: formData });
	const ack = await response.json();
	if (!session.uuid) {
		promoteToSession(ack.session);
		openLiveStream();
	}
}

async function init() {
	const form = document.getElementById('chat-form');
	if (!form) return;
	const sessionId = form.dataset.sessionId || null;
	form.addEventListener('submit', submitLiveChat);
	const json = sessionId
		? await (await fetch(`/api/sessions/${sessionId}`)).json()
		: { uuid: null, archived: false, status: 'idle', settings: {}, messages: [] };
	session = new Session(json);
	liveSessionView = new SessionView(ensureMessagesContainer(), session);
	if (session.uuid) openLiveStream();
}

function formatNumber(n) {
	if (n === null || n === undefined) return "";
	if (n === 0) return "0";
	if (n % 1024 === 0) {
		if (n < 1024) return `${Math.trunc(n)} B`;
		const units = ["KiB", "MiB", "GiB", "TiB"];
		let i = -1;
		while (n >= 1024 && i < units.length - 1) {
			n /= 1024;
			i += 1;
		}
		const s = n.toFixed(1).replace(/0+$/, "").replace(/\.$/, "");
		return `${s} ${units[i]}`;
	} else {
		if (n < 1000) return String(Math.trunc(n));
		const units = ["K", "M", "B", "T"];
		let i = -1;
		while (n >= 1000 && i < units.length - 1) {
			n /= 1000;
			i += 1;
		}
		const s = n.toFixed(1).replace(/0+$/, "").replace(/\.$/, "");
		return `${s}${units[i]}`;
	}
}
