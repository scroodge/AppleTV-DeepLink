/** Type definitions for API responses and data structures */

export interface DeviceInfo {
	device_id: string;
	name: string;
	address: string;
	protocols: string[];
	identifier?: string;
	device_type?: 'modern' | 'legacy';
}

export interface PairedDevice {
	id: number;
	device_id: string;
	name: string;
	address: string;
	protocols: string[];
	/** Protocols that have been paired (e.g. ["airplay", "companion"]) */
	paired_protocols?: string[];
	is_paired?: boolean; // True if device has actual credentials (was paired)
	last_seen?: string;
	created_at: string;
}

export interface DefaultDevice {
	device_id: string | null;
	name?: string;
	address?: string;
	protocols?: string[];
}

export interface ApiResponse<T = any> {
	ok: boolean;
	data?: T;
	error?: {
		code: string;
		message: string;
		details?: any;
	};
}

export interface PairingStatus {
	status: 'PIN_REQUIRED' | 'CREDENTIALS_REQUIRED' | 'COMPLETED';
	message: string;
}

export interface ToastMessage {
	id: string;
	message: string;
	type: 'success' | 'error' | 'info';
	duration?: number;
}

export interface ActivityEntry {
	ts: string;
	status: 'start' | 'success' | 'error';
	url?: string;
	device?: string;
	message: string;
	method?: string;
	merge_used?: boolean;
}
