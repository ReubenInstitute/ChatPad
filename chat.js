
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
