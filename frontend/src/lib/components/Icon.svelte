<script lang="ts">
	// Maps the string icon ids declared by attachments/manifests to lucide-svelte
	// components. Icon ids stay strings (the backend declares them), so this is the
	// single place where a name is resolved to a real Lucide icon. Unknown ids fall
	// back to a generic square so the sidebar never breaks.
	import Square from 'lucide-svelte/icons/square';
	import Star from 'lucide-svelte/icons/star';
	import SquareCheckBig from 'lucide-svelte/icons/square-check-big';
	import FileText from 'lucide-svelte/icons/file-text';
	import Home from 'lucide-svelte/icons/house';
	import List from 'lucide-svelte/icons/list';
	import Grid from 'lucide-svelte/icons/grid-2x2';
	import Folder from 'lucide-svelte/icons/folder';
	import FolderPlus from 'lucide-svelte/icons/folder-plus';
	import File from 'lucide-svelte/icons/file';
	import Image from 'lucide-svelte/icons/image';
	import Upload from 'lucide-svelte/icons/upload';
	import Download from 'lucide-svelte/icons/download';
	import Trash from 'lucide-svelte/icons/trash';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import SquarePen from 'lucide-svelte/icons/square-pen';
	import X from 'lucide-svelte/icons/x';
	import Globe from 'lucide-svelte/icons/globe';
	import Terminal from 'lucide-svelte/icons/terminal';
	import Menu from 'lucide-svelte/icons/menu';
	import ChevronLeft from 'lucide-svelte/icons/chevron-left';
	import ChevronRight from 'lucide-svelte/icons/chevron-right';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import ChevronUp from 'lucide-svelte/icons/chevron-up';
	import Pause from 'lucide-svelte/icons/pause';
	import Play from 'lucide-svelte/icons/play';
	import User from 'lucide-svelte/icons/user';
	import Users from 'lucide-svelte/icons/users';
	import LogOut from 'lucide-svelte/icons/log-out';
	import Activity from 'lucide-svelte/icons/activity';
	import Cpu from 'lucide-svelte/icons/cpu';
	import Thermometer from 'lucide-svelte/icons/thermometer';
	import Zap from 'lucide-svelte/icons/zap';
	import HardDrive from 'lucide-svelte/icons/hard-drive';
	import Clock from 'lucide-svelte/icons/clock';
	import Clock4 from 'lucide-svelte/icons/clock-4';
	import MemoryStick from 'lucide-svelte/icons/memory-stick';
	import TriangleAlert from 'lucide-svelte/icons/triangle-alert';
	import Check from 'lucide-svelte/icons/check';
	import Mail from 'lucide-svelte/icons/mail';
	import MailPlus from 'lucide-svelte/icons/mail-plus';
	import RefreshCw from 'lucide-svelte/icons/refresh-cw';
	import Lock from 'lucide-svelte/icons/lock';
	import Video from 'lucide-svelte/icons/video';
	import Search from 'lucide-svelte/icons/search';
	import Bell from 'lucide-svelte/icons/bell';
	import BellOff from 'lucide-svelte/icons/bell-off';
	import Calendar from 'lucide-svelte/icons/calendar';
	import Sparkles from 'lucide-svelte/icons/sparkles';
	import ZoomIn from 'lucide-svelte/icons/zoom-in';
	import ZoomOut from 'lucide-svelte/icons/zoom-out';
	import ImageOff from 'lucide-svelte/icons/image-off';
	import Plus from 'lucide-svelte/icons/plus';
	import Maximize from 'lucide-svelte/icons/maximize';
	import Minimize from 'lucide-svelte/icons/minimize';
	import Sun from 'lucide-svelte/icons/sun';
	import Moon from 'lucide-svelte/icons/moon';
	import Phone from 'lucide-svelte/icons/phone';
	import MapPin from 'lucide-svelte/icons/map-pin';
	import Contact from 'lucide-svelte/icons/contact';
	import WrapText from 'lucide-svelte/icons/text-wrap';
	import Hash from 'lucide-svelte/icons/hash';
	import Inbox from 'lucide-svelte/icons/inbox';
	import MessageCircle from 'lucide-svelte/icons/message-circle';
	import Paperclip from 'lucide-svelte/icons/paperclip';
	import Send from 'lucide-svelte/icons/send';
	import Key from 'lucide-svelte/icons/key';
	import type { ComponentType } from 'svelte';

	let { name = 'square', size = 18 }: { name?: string; size?: number } = $props();

	const icons: Record<string, ComponentType> = {
		square: Square,
		star: Star,
		'check-square': SquareCheckBig,
		'file-text': FileText,
		home: Home,
		list: List,
		grid: Grid,
		folder: Folder,
		'folder-plus': FolderPlus,
		file: File,
		image: Image,
		upload: Upload,
		download: Download,
		trash: Trash,
		'trash-2': Trash2,
		edit: SquarePen,
		x: X,
		globe: Globe,
		terminal: Terminal,
		menu: Menu,
		'chevron-left': ChevronLeft,
		'chevron-right': ChevronRight,
		'chevron-down': ChevronDown,
		'chevron-up': ChevronUp,
		pause: Pause,
		play: Play,
		user: User,
		users: Users,
		'log-out': LogOut,
		activity: Activity,
		cpu: Cpu,
		thermometer: Thermometer,
		zap: Zap,
		'hard-drive': HardDrive,
		clock: Clock,
		clock4: Clock4,
		'memory-stick': MemoryStick,
		'alert-triangle': TriangleAlert,
		check: Check,
		mail: Mail,
		'mail-plus': MailPlus,
		'refresh-cw': RefreshCw,
		lock: Lock,
		video: Video,
		search: Search,
		bell: Bell,
		'bell-off': BellOff,
		calendar: Calendar,
		sparkles: Sparkles,
		'zoom-in': ZoomIn,
		'zoom-out': ZoomOut,
		'image-off': ImageOff,
		plus: Plus,
		maximize: Maximize,
		minimize: Minimize,
		sun: Sun,
		moon: Moon,
		phone: Phone,
		'map-pin': MapPin,
		contact: Contact,
		'wrap-text': WrapText,
		hash: Hash,
		inbox: Inbox,
		'message-circle': MessageCircle,
		paperclip: Paperclip,
		send: Send,
		key: Key
	};

	const Glyph = $derived(icons[name] ?? icons.square);
</script>

<Glyph {size} aria-hidden="true" />
