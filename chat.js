
function copyContent(element) {
	const expandedDiv = element.parentElement;
	const text = expandedDiv.querySelector('.content').textContent;
	navigator.clipboard.writeText(text);
}


function initializeChatView() {
	const messages = document.querySelectorAll('.message');

	for (let i = 0; i < messages.length - 1; i++) {
		const message = messages[i];
		const containers = message.querySelectorAll('.prompt, .reasoning, .error, .response');

		containers.forEach(container => {
			const expandedDiv = container.children[0];
			const collapsedDiv = container.children[1];

			if (expandedDiv && collapsedDiv) {
				expandedDiv.style.display = 'none';
				collapsedDiv.style.display = 'block';
			}
		});
	}

	window.scrollTo(0, document.body.scrollHeight);
}














function collapse(element) {
	const container = element.parentElement.parentElement;
	const expanded = container.children[0];
	const collapsed = container.children[1];
	expanded.style.display = 'none';
	collapsed.style.display = 'block';
}
function expand(element) {
	const container = element.parentElement.parentElement;
	const expanded = container.children[0];
	const collapsed = container.children[1];
	expanded.style.display = 'block';
	collapsed.style.display = 'none';
}	









async function handleStreamingSubmit(event) {
	event.preventDefault();

	const form = event.currentTarget;
	const sessionId = window.location.pathname.split('/').pop();
	const template = document.getElementById('message-template');
	const newMsg = document.importNode(template.content, true);
	const messageDiv = newMsg.querySelector('.message');

	// Fill the prompt
	const prompt = form.querySelector('#prompt').value;
	messageDiv.querySelector('.prompt .content').textContent = prompt;
	const promptShort = prompt.slice(0, 30) + (prompt.length > 30 ? '...' : '');
	messageDiv.querySelector('.prompt > div:last-child span').textContent = promptShort;

	document.querySelector('.messages').appendChild(messageDiv);

	const respContent = messageDiv.querySelector('.response .content');
	const reasContent = messageDiv.querySelector('.reasoning .content');
	const reasBlock = messageDiv.querySelector('.reasoning');

	// Send the form data to the streaming endpoint
	const formData = new FormData(form);
	const response = await fetch(`/stream/${sessionId}`, { method: 'POST', body: formData });

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split('\n');
		buffer = lines.pop();
		for (const line of lines) {
			if (line.startsWith('data: ')) {
				const data = JSON.parse(line.slice(6));
				if (data.content) {
					respContent.textContent += data.content;
					const short = respContent.textContent.slice(0, 30) + (respContent.textContent.length > 30 ? '...' : '');
					messageDiv.querySelector('.response > div:last-child span').textContent = short;
				}
				if (data.reasoning) {
					reasBlock.style.display = 'block';
					reasContent.textContent += data.reasoning;
					const short = reasContent.textContent.slice(0, 30) + (reasContent.textContent.length > 30 ? '...' : '');
					messageDiv.querySelector('.reasoning > div:last-child span').textContent = short;
				}
			}
		}
	}

	// Collapse all older messages, keep the new one expanded
	initializeChatView();
}
