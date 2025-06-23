// HTML escaping function
function escapeHtml(unsafe) {
	if (!unsafe) return '';
	return unsafe.toString()
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}

// Safe markdown parser
function simpleMarkdown(text) {
	if (typeof marked !== 'undefined') {
		return marked.parse(text);
	}
	const escaped = escapeHtml(text || '');
	return escaped
		.replace(/^# (.*)$/gm, (_, txt) => `<h1>${txt}</h1>`)
		.replace(/^## (.*)$/gm, (_, txt) => `<h2>${txt}</h2>`)
		.replace(/\*\*(.*?)\*\*/g, (_, txt) => `<strong>${txt}</strong>`)
		.replace(/\*(.*?)\*/g, (_, txt) => `<em>${txt}</em>`)
		.replace(/`(.*?)`/g, (_, txt) => `<code>${txt}</code>`)
		.replace(/\n/g, '<br>');
}

// DOM elements
const messagesDiv = document.getElementById('chat-messages');
const input = document.querySelector('input[name="message"]');
const sendBtn = document.getElementById('send-btn');
const reasoningCheckbox = document.getElementById('use_reasoning');
const modelIndicator = document.getElementById('model-indicator');
const balanceDisplay = document.getElementById('balance-display');
const balanceText = document.getElementById('balance-text');

function scrollToBottom() {
	messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function addMessage(content, role) {
	const messageDiv = document.createElement('div');
	messageDiv.className = `message ${role}-message`;
	
	if(role === 'assistant') {
		messageDiv.innerHTML = `
			<div class="reasoning-content"></div>
			<div class="content"></div>
		`;
	} else {
		messageDiv.innerHTML = `<div class="content">${simpleMarkdown(content)}</div>`;
	}

	messagesDiv.appendChild(messageDiv);
	scrollToBottom();
	return messageDiv;
}

function updateMessage(messageDiv, content, reasoning) {
	if(reasoning && reasoning.trim() !== '') {
		const reasoningDiv = messageDiv.querySelector('.reasoning-content');
		reasoningDiv.innerHTML = simpleMarkdown(reasoning);
	}
	if(content && content.trim() !== '') {
		const contentDiv = messageDiv.querySelector('.content');
		contentDiv.innerHTML = simpleMarkdown(content);
	}
	scrollToBottom();
}

async function updateBalance() {
	try {
		const response = await fetch('/balance');
		const data = await response.json();
		
		if (data && data.balance_infos && data.balance_infos.length > 0) {
			const balance = data.balance_infos[0].total_balance;
			balanceText.textContent = `${balance} credits`;
		} else {
			balanceText.textContent = 'Balance unavailable';
		}
	} catch(e) {
		balanceText.textContent = 'Error loading balance';
		console.error('Balance update error:', e);
	}
}

async function sendMessage() {
	const message = input.value.trim();
	if(!message) return;

	const useReasoning = reasoningCheckbox.checked;
	addMessage(message, 'user');
	input.value = '';
	
	const botMessage = addMessage('Thinking...', 'assistant');

	try {
		const response = await fetch('/chat', {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({
				message: message,
				use_reasoning: useReasoning
			})
		});

		const data = await response.json();
		if (!response.ok) {
			throw new Error(data.error || 'Unknown error');
		}
		
		updateMessage(botMessage, data.content, data.reasoning);
		
		// Update balance after response
		if (data.balance && data.balance.balance_infos && data.balance.balance_infos.length > 0) {
			const balance = data.balance.balance_infos[0].total_balance;
			balanceText.textContent = `${balance} credits`;
		} else {
			await updateBalance();
		}
		
	} catch(e) {
		updateMessage(botMessage, 'Error: ' + escapeHtml(e.message), '');
	}
}

// Event listeners
sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keypress', function(e) {
	if(e.key === 'Enter') sendMessage();
});

reasoningCheckbox.addEventListener('change', function() {
	modelIndicator.textContent = this.checked ? 'Reasoning Model' : 'Standard Model';
});

// Initialize
scrollToBottom();
updateBalance();  // Get initial balance
