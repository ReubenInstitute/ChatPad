
function copyContent(element) {
	const expandedDiv = element.parentElement;
	const text = expandedDiv.querySelector('.content').textContent;
	navigator.clipboard.writeText(text);
}


function initializeChatView() {
	const messages = document.querySelectorAll('.message');

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
