// Mirror of the backend UI descriptor vocabulary (backend/raspy/core/ui.py).
// The renderer walks these nodes; the backend owns the structure.

export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface Action {
	method: Method;
	path: string;
	body?: Record<string, unknown>;
}

export interface UINode {
	type: string;
	// containers
	children?: UINode[];
	title?: string;
	direction?: 'row' | 'column';
	gap?: number;
	align?: string;
	justify?: string;
	wrap?: boolean;
	level?: 1 | 2;
	interactive?: boolean;
	// content
	text?: string;
	role?: string;
	variant?: string;
	variant_bind?: string;
	hide_when_empty?: boolean;
	empty_label?: string;
	size?: string;
	bind?: string;
	// inputs
	name?: string;
	placeholder?: string;
	label?: string;
	kind?: string;
	options?: Array<{ value: string; label: string }>;
	action?: Action;
	// collections
	source?: string;
	item?: UINode;
	key?: string;
	empty?: string;
	/** When set, list rows are drag-reorderable; this action receives `{order:[…]}`. */
	reorder?: Action;
	columns?: Array<{ key: string; label: string }>;
	// file manager
	list_source?: string;
}

export interface AttachmentManifest {
	id: string;
	title: string;
	icon: string;
	version: string;
	ui: UINode | null;
	ui_version: string;
	bundle: string | null;
}

export interface Manifest {
	version: string;
	attachments: AttachmentManifest[];
}
