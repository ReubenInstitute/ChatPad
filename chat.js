
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
	const list = document.querySelector('.model-list');
	const collapsed = list.classList.toggle('collapsed');
	if (!collapsed) {
		document.querySelector('.tools-list').classList.add('collapsed');
	}
}

function toggleToolsList() {
	const list = document.querySelector('.tools-list');
	const collapsed = list.classList.toggle('collapsed');
	if (!collapsed) {
		document.querySelector('.model-list').classList.add('collapsed');
	}
}

function selectModel(el) {
	document.querySelectorAll('.model-toggle.enabled').forEach(other => other.classList.remove('enabled'));
	el.classList.add('enabled');
	document.getElementById('model-input').value = el.dataset.id;
	document.getElementById('model-header').textContent = el.dataset.id;
	document.querySelector('.model-list').classList.add('collapsed');
	saveSelectedModel();
}

function restoreSelectedModel() {
	const saved = localStorage.getItem(MODEL_STORAGE_KEY);
	if (!saved) return;
	const el = document.querySelector(`.model-toggle[data-id="${CSS.escape(saved)}"]`);
	if (el) selectModel(el);
}

function saveSelectedModel() {
	localStorage.setItem(MODEL_STORAGE_KEY, document.getElementById('model-input').value);
}

document.addEventListener('DOMContentLoaded', function() {
	restoreEnabledTools();
	restoreSelectedModel();
	restoreReasoning();
});
