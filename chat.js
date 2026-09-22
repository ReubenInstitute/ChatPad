
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

const TOOLS_STORAGE_KEY = 'chatpad-enabled-tools';

function toggleTool(el) {
	const input = el.nextElementSibling;
	const enabled = el.classList.toggle('enabled');
	input.disabled = !enabled;
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

document.addEventListener('DOMContentLoaded', function() {
	restoreEnabledTools();
	const form = document.querySelector('.chatbox form');
	if (form) {
		form.addEventListener('submit', saveEnabledTools);
	}
});
