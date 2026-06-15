// Move an element to document.body (or a chosen target) for its lifetime, so it
// escapes any ancestor that would otherwise trap it — a `transform`,
// `backdrop-filter`, or `filter` on a parent creates a containing block that makes
// `position: fixed` resolve to that parent instead of the viewport. A portal lets
// a fullscreen overlay truly cover the screen no matter where it's declared.
//
// Usage: <div use:portal> … </div>  (or  use:portal={someTargetEl})

export function portal(node: HTMLElement, target: HTMLElement | undefined = undefined) {
	let host: HTMLElement;
	function mount(t?: HTMLElement) {
		host = t ?? document.body;
		host.appendChild(node);
	}
	mount(target);
	return {
		update(t?: HTMLElement) {
			mount(t);
		},
		destroy() {
			node.parentNode?.removeChild(node);
		}
	};
}
