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

	resume(permission) {
		fetch(`/api/sessions/${this.uuid}/resume`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ permission }),
		})
	}

	stop() {
		fetch(`/api/sessions/${this.uuid}/stop`, { method: 'POST' })
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
		this.collapseAllButLast()
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
		} else if (this.message_views.length > 0) {
			this.message_views[this.message_views.length - 1].update()
		}
		this.collapseAllButLast()
	}

	// At any point, only the single last turn of the single last message stays
	// expanded - everything earlier is collapsed to one line, so scrolling back
	// through history never means scrolling through full text.
	collapseAllButLast() {
		const blocks = Array.from(this.container.querySelectorAll('.prompt, .reasoning, .tool, .error, .response'))
		blocks.forEach((el, i) => el.classList.toggle('collapsed', i !== blocks.length - 1))
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
		action.onclick = () => this.container.classList.contains('hidden') ? this.unhide() : this.hide()
		this.container.appendChild(action)
		iconify(this.container)
	}

	// hidden is backend-owned: it decides whether this message is sent as
	// history to the model. The DOM class is only a reflection of that state,
	// exactly like a Chatbox setting - the write is the save.
	hide() {
		this.container.classList.add('hidden')
		fetch(`/api/sessions/${this.message.session.uuid}/messages/${this.message.uuid}/hide`, { method: 'POST' })
	}

	unhide() {
		this.container.classList.remove('hidden')
		fetch(`/api/sessions/${this.message.session.uuid}/messages/${this.message.uuid}/unhide`, { method: 'POST' })
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
		div.onclick = () => toggleCollapsed(div)

		const content = document.createElement('div')
		content.className = 'content'
		div.appendChild(content)

		const action = document.createElement('span')
		action.className = 'action'
		action.title = 'Copy'
		action.innerHTML = '<i data-lucide="copy"></i>'
		action.onclick = (e) => { e.stopPropagation(); this.copy(action) }
		div.appendChild(action)

		this.container.appendChild(div)
		iconify(div)
		return div
	}

	copy(button) {
		const content = button.parentElement.querySelector('.content')
		const clone = content.cloneNode(true)
		clone.querySelectorAll('.turn-time').forEach(el => el.remove())
		navigator.clipboard.writeText(clone.textContent.trim())
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
		this.container.onclick = () => toggleCollapsed(this.container)

		const content = document.createElement('div')
		content.className = 'content'
		this.container.appendChild(content)

		const action = document.createElement('span')
		action.className = 'action'
		action.title = 'Copy'
		action.innerHTML = '<i data-lucide="copy"></i>'
		action.onclick = (e) => { e.stopPropagation(); this.copy(action) }
		this.container.appendChild(action)
		iconify(this.container)

		this.update()
	}

	copy(button) {
		const content = button.parentElement.querySelector('.content')
		const clone = content.cloneNode(true)
		clone.querySelectorAll('.turn-time').forEach(el => el.remove())
		navigator.clipboard.writeText(clone.textContent.trim())
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

function toggleCollapsed(container) {
	if (window.getSelection().toString()) return
	container.classList.toggle('collapsed')
}

// fetch_url was split into get_url and download_url
const LEGACY_TOOLS = { 'fetch_url': ['get_url', 'download_url'] }

class Chatbox {
	constructor(container, session) {
		this.container = container
		this.session = session
	}

	init() {
		this.tools = this.session.settings.tools || []
		this.think = this.session.settings.think == null ? true : this.session.settings.think
		this.mode = this.session.settings.mode || 'auto'
		if (this.session.settings.model) this.model = this.session.settings.model
		if (this.session.settings.system_model) this.system_model = this.session.settings.system_model
		this.archived = this.session.archived
	}

	toggleModelList() {
		const list = this.container.querySelector('#model-menu')
		const hidden = list.classList.toggle('hidden')
		if (!hidden) this.container.querySelector('#tools-menu').classList.add('hidden')
	}

	toggleSystemModelList() {
		const hidden = this.container.querySelector('#system-model-menu').classList.toggle('hidden')
		this.container.querySelector('#system-model-link').classList.toggle('hidden', !hidden)
	}

	toggleToolsList() {
		const list = this.container.querySelector('#tools-menu')
		const hidden = list.classList.toggle('hidden')
		if (!hidden) this.container.querySelector('#model-menu').classList.add('hidden')
	}

	// Mirror the picked option's icon and name onto the collapsed menu header, so
	// the closed menu shows which model is selected. Options carry their icon as a
	// nested <img class="model-icon-small"> (absent for the "none" option); the
	// header is an <img> + <span> pair so the icon can be swapped in and out.
	setHeaderModel(header, source) {
		const sourceIcon = source.querySelector('img.model-icon-small')
		const headerIcon = header.querySelector('img.model-icon-small')
		const nameEl = header.querySelector('span')
		if (headerIcon) {
			if (sourceIcon) {
				headerIcon.src = sourceIcon.src
				headerIcon.hidden = false
			} else {
				headerIcon.removeAttribute('src')
				headerIcon.hidden = true
			}
		}
		if (nameEl) nameEl.textContent = source.dataset.name
	}

	toggleTool(el) {
		const input = el.nextElementSibling
		const enabled = el.classList.toggle('enabled')
		input.disabled = !enabled
		this.tools = Array.from(this.container.querySelectorAll('.tool-toggle.enabled')).map(o => o.dataset.name)
	}

	get tools() {
		return Array.from(this.container.querySelectorAll('.tool-toggle.enabled')).map(el => el.dataset.name)
	}

	set tools(names) {
		const current = Array.from(this.container.querySelectorAll('.tool-toggle')).map(el => el.dataset.name)
		const wanted = new Set()
		names.forEach(name => {
			if (current.includes(name)) wanted.add(name)
			;(LEGACY_TOOLS[name] || []).forEach(n => wanted.add(n))
		})
		this.container.querySelectorAll('.tool-toggle').forEach(el => {
			const input = el.nextElementSibling
			const on = wanted.has(el.dataset.name)
			el.classList.toggle('enabled', on)
			input.disabled = !on
		})
		this.session.settings.tools = Array.from(wanted)
		this.session.settings.save()
	}

	toggleReasoning(el) {
		this.think = el.classList.toggle('enabled')
	}

	get think() {
		const el = this.container.querySelector('#reasoning-toggle')
		return el ? el.classList.contains('enabled') : null
	}

	set think(value) {
		const el = this.container.querySelector('#reasoning-toggle')
		if (el) {
			el.classList.toggle('enabled', value)
			el.nextElementSibling.disabled = !value
		}
		this.session.settings.think = value
		this.session.settings.save()
	}

	selectModel(el) {
		this.model = el.dataset.id
	}

	get model() {
		const el = this.container.querySelector('[name="model"]')
		return el ? el.value : null
	}

	set model(value) {
		this.container.querySelectorAll('#model-menu .model-toggle.enabled').forEach(o => o.classList.remove('enabled'))
		const option = this.container.querySelector(`#model-menu .model-toggle[data-id="${CSS.escape(value)}"]`)
		if (option) {
			option.classList.add('enabled')
			this.setHeaderModel(this.container.querySelector('#model-link'), option)
		}
		this.container.querySelector('[name="model"]').value = value
		this.container.querySelector('#model-menu').classList.add('hidden')
		this.session.settings.model = value
		this.session.settings.save()
	}

	selectSystemModel(el) {
		this.system_model = el.dataset.id
	}

	get system_model() {
		const el = this.container.querySelector('#system-model-menu .model-toggle.enabled')
		return el ? el.dataset.id : null
	}

	set system_model(value) {
		this.container.querySelectorAll('#system-model-menu .model-toggle.enabled').forEach(o => o.classList.remove('enabled'))
		const link = this.container.querySelector('#system-model-link')
		const option = value && this.container.querySelector(`#system-model-menu .model-toggle[data-id="${CSS.escape(value)}"]`)
		if (option) {
			option.classList.add('enabled')
			this.setHeaderModel(link, option)
			link.classList.remove('hidden')
		}
		this.container.querySelector('#system-model-menu').classList.add('hidden')
		this.session.settings.system_model = value
		this.session.settings.save()
	}

	toggleMode(el) {
		this.mode = el.dataset.mode === 'manual' ? 'auto' : 'manual'
	}

	get mode() {
		const el = this.container.querySelector('#mode-toggle')
		return el ? el.dataset.mode : null
	}

	set mode(value) {
		const el = this.container.querySelector('#mode-toggle')
		if (el) {
			el.dataset.mode = value
			el.classList.toggle('enabled', value === 'manual')
			el.title = value === 'manual' ? 'Manual: approve each tool call' : 'Auto: tools run without approval'
		}
		this.container.querySelector('[name="mode"]').value = value
		this.session.settings.mode = value
		this.session.settings.save()
	}

	toggleArchive() {
		this.archived = !this.archived
	}

	get archived() {
		return this.session.archived
	}

	set archived(value) {
		this.session.archived = value
		const el = this.container.querySelector('#archive-toggle')
		if (el) el.innerHTML = value ? '<i data-lucide="archive-restore"></i>' : '<i data-lucide="trash-2"></i>'
		this.container.classList.toggle('archived', value)
		iconify(this.container)
		fetch(`/api/sessions/${this.session.uuid}/${value ? 'archive' : 'unarchive'}`, { method: 'POST' })
	}

	refreshModels() {
		fetch('/api/refresh-models', { method: 'POST' }).then(() => location.reload())
	}
}

function iconify(root) {
	lucide.createIcons({ root })
}

// Follow the stream only while the reader is at the bottom, so scrolling up to
// read is never yanked back down by an incoming patch. The flag is driven by
// real scroll events rather than measured at paint time, so content growing
// cannot by itself push the reader out of the follow zone.
let followStream = true

function initFollowStream() {
	const update = () => {
		followStream = document.body.scrollHeight - window.innerHeight - window.scrollY < 120
	}
	window.addEventListener('scroll', update, { passive: true })
	update()
}

function scrollIfAtBottom() {
	if (followStream) window.scrollTo(0, document.body.scrollHeight)
}

function ensureMessagesContainer() {
	let el = document.querySelector('.session')
	if (el) return el
	el = document.createElement('div')
	el.className = 'session'
	document.querySelector('main').appendChild(el)
	return el
}

let session = null
let liveSessionView = null
let chatbox = null
let permissionBox = null

function startLiveTurn(record) {
	session.messages.push(new Message({ uuid: record.uuid, hidden: false, turns: [] }, session))
	liveSessionView.update()
}

function currentMessage() {
	return session.messages[session.messages.length - 1]
}

function currentTurn() {
	return currentMessage().turns[currentMessage().turns.length - 1]
}

function applyPatch(turn, target, patchText) {
	const dmp = new diff_match_patch()
	const patches = dmp.patch_fromText(patchText)
	const [newHtml] = dmp.patch_apply(patches, turn[target] || '')
	turn[target] = newHtml
}

function toolLabel(record, call) {
	const labels = record.labels || {}
	return labels[call.id] || `${call.function.name}(${call.function.arguments})`
}

async function renderMarkdown(text) {
	const response = await fetch('/api/markdown', { method: 'POST', body: new URLSearchParams({ text }) })
	return response.text()
}

async function handleStreamRecord(record) {
	if (record.type === 'status') {
		session.status = record.status
		if (permissionBox) { permissionBox.remove(); permissionBox = null }
		return
	}
	if (record.type === 'prompt') {
		startLiveTurn(record)
		currentMessage().turns.push(new MessageTurn({ prompt: record.content }, currentMessage()))
	} else if (!session || !session.messages.length) {
		return
	} else if (record.type === 'html_patch') {
		applyPatch(currentTurn(), record.target, record.patch)
	} else if (record.type === 'reasoning') {
		currentTurn().reasoning = await renderMarkdown(record.content)
	} else if (record.type === 'response') {
		if (record.content) currentTurn().response = await renderMarkdown(record.content)
		if (record.model) currentTurn().model = record.model
		if (record.model_name) currentTurn().model_name = record.model_name
		if (record.icon) currentTurn().icon = record.icon
		if (record.usage) currentTurn().usage = record.usage
		if (record.context_length) currentTurn().context_length = record.context_length
	} else if (record.type === 'error') {
		currentTurn().error = record.error
	} else if (record.type === 'tool_call') {
		record.tool_calls.forEach(call => {
			currentMessage().turns.push(new ToolTurn({
				tool: toolLabel(record, call),
				arguments: call.function.arguments,
				result: null,
				call_id: call.id,
			}, currentMessage()))
		})
	} else if (record.type === 'tool_result') {
		const turn = currentMessage().turns.find(t => t instanceof ToolTurn && t.call_id === record.tool_call_id)
		if (turn) turn.result = { content: record.content, error: record.error }
	} else if (record.type === 'await_approval') {
		session.status = 'awaiting'
		permissionBox = document.createElement('div')
		permissionBox.className = 'permissionbox'
		;[['Accept', () => session.resume(true)], ['Deny', () => session.resume(false)], ['Stop', () => session.stop()]].forEach(([label, action]) => {
			const button = document.createElement('button')
			button.type = 'button'
			button.textContent = label
			button.onclick = action
			permissionBox.appendChild(button)
		})
		ensureMessagesContainer().appendChild(permissionBox)
	}
	liveSessionView.update()
	scrollIfAtBottom()
}

async function openLiveStream() {
	const response = await fetch(`/api/sessions/${session.uuid}/stream`)
	const reader = response.body.getReader()
	const decoder = new TextDecoder()
	let buffer = ''
	while (true) {
		const { done, value } = await reader.read()
		if (done) break
		buffer += decoder.decode(value, { stream: true })
		const parts = buffer.split('\n\n')
		buffer = parts.pop()
		for (const part of parts) {
			if (!part.startsWith('data: ')) continue
			await handleStreamRecord(JSON.parse(part.slice(6)))
		}
	}
}

async function submitLiveChat(event) {
	event.preventDefault()
	const form = event.currentTarget
	const formData = new FormData(form)
	const promptEl = form.querySelector('textarea[name="prompt"]')
	promptEl.value = ''

	const url = session ? `/api/sessions/${session.uuid}/message` : '/api/message'
	const response = await fetch(url, { method: 'POST', body: formData })
	const ack = await response.json()
	if (!session) {
		session = new Session({ uuid: ack.session, archived: false, status: 'idle', settings: {}, messages: [] })
		liveSessionView = new SessionView(ensureMessagesContainer(), session)
		chatbox = new Chatbox(document.querySelector('.chatbox'), session)
		chatbox.init()
		history.pushState(null, '', `/chat/${ack.session}`)
		openLiveStream()
	}
}

async function init() {
	const form = document.getElementById('chat-form')
	if (!form) return
	const sessionId = form.dataset.sessionId || null
	form.addEventListener('submit', submitLiveChat)
	if (!sessionId) return
	const json = await (await fetch(`/api/sessions/${sessionId}`)).json()
	session = new Session(json)
	liveSessionView = new SessionView(ensureMessagesContainer(), session)
	chatbox = new Chatbox(document.querySelector('.chatbox'), session)
	chatbox.init()
	openLiveStream()
}

document.addEventListener('DOMContentLoaded', async function() {
	await init()
	initFollowStream()
	lucide.createIcons()
})

function formatNumber(n) {
	if (n === null || n === undefined) return ""
	if (n === 0) return "0"
	if (n % 1024 === 0) {
		if (n < 1024) return `${Math.trunc(n)} B`
		const units = ["KiB", "MiB", "GiB", "TiB"]
		let i = -1
		while (n >= 1024 && i < units.length - 1) {
			n /= 1024
			i += 1
		}
		const s = n.toFixed(1).replace(/0+$/, "").replace(/\.$/, "")
		return `${s} ${units[i]}`
	} else {
		if (n < 1000) return String(Math.trunc(n))
		const units = ["K", "M", "B", "T"]
		let i = -1
		while (n >= 1000 && i < units.length - 1) {
			n /= 1000
			i += 1
		}
		const s = n.toFixed(1).replace(/0+$/, "").replace(/\.$/, "")
		return `${s}${units[i]}`
	}
}
