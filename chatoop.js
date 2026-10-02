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

class Session {
	constructor(json) {
		this.uuid = json.uuid
		this.archived = json.archived
		this.messages = json.messages.map(m => new Message(m, this))
	}
}

class App {
	constructor() {
		this.id = location.pathname.split("/").pop()
	}

	async load() {
		if (!this.id) {
			this.sessions = await (await fetch("/API/sessions")).json()
			return
		}
		const response = await fetch(`/API/sessions/${this.id}`)
		this.session = new Session(await response.json())
	}
}
