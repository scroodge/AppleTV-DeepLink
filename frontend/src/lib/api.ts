/** API client for backend communication */
import { browser } from '$app/environment';
import type { ApiResponse, DeviceInfo, PairedDevice, DefaultDevice, PairingStatus, ActivityEntry } from './types';

function getApiUrl(): string {
	if (typeof window === 'undefined') return 'http://localhost:8100';
	const env = import.meta.env.PUBLIC_API_URL;
	if (env) return env;
	// Без env: тот же хост, порт 8100 (чтобы работало при открытии по IP, напр. http://192.168.1.5:3000)
	return `${window.location.protocol}//${window.location.hostname}:8100`;
}
const API_URL = getApiUrl();

async function request<T>(
	endpoint: string,
	options: RequestInit = {}
): Promise<ApiResponse<T>> {
	if (!browser) {
		// Return error response during SSR
		return {
			ok: false,
			error: {
				code: 'SSR_ERROR',
				message: 'API calls can only be made on the client side',
			},
		};
	}

	try {
		const response = await fetch(`${API_URL}${endpoint}`, {
			headers: {
				'Content-Type': 'application/json',
				...options.headers,
			},
			...options,
		});

		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}

		return await response.json();
	} catch (error) {
		console.error('API request failed:', error);
		return {
			ok: false,
			error: {
				code: 'NETWORK_ERROR',
				message: error instanceof Error ? error.message : 'Unknown error',
			},
		};
	}
}

export const api = {
	async scanDevices(): Promise<ApiResponse<{ devices: DeviceInfo[] }>> {
		return request<{ devices: DeviceInfo[] }>('/api/appletv/scan');
	},

	async getPairedDevices(): Promise<ApiResponse<{ devices: PairedDevice[] }>> {
		return request<{ devices: PairedDevice[] }>('/api/appletv/devices');
	},

	async startPairing(
		deviceId: string,
		protocol: string
	): Promise<ApiResponse<PairingStatus>> {
		return request<PairingStatus>(`/api/appletv/${deviceId}/pair/start`, {
			method: 'POST',
			body: JSON.stringify({ protocol }),
		});
	},

	async submitPin(deviceId: string, pin: string): Promise<ApiResponse<PairingStatus>> {
		return request<PairingStatus>(`/api/appletv/${deviceId}/pair/pin`, {
			method: 'POST',
			body: JSON.stringify({ pin }),
		});
	},

	async playUrl(
		url: string,
		deviceId?: string,
		quality?: string
	): Promise<ApiResponse<{ status: string; message: string }>> {
		return request<{ status: string; message: string }>('/api/appletv/play', {
			method: 'POST',
			body: JSON.stringify({ url, device_id: deviceId, quality: quality || 'auto' }),
		});
	},

	async stopPlayback(): Promise<ApiResponse<{ status: string; message: string }>> {
		return request<{ status: string; message: string }>('/api/appletv/stop', {
			method: 'POST',
		});
	},

	async setDefaultDevice(deviceId: string): Promise<ApiResponse<{ device_id: string }>> {
		return request<{ device_id: string }>('/api/appletv/default', {
			method: 'POST',
			body: JSON.stringify({ device_id: deviceId }),
		});
	},

	async getDefaultDevice(): Promise<ApiResponse<DefaultDevice>> {
		return request<DefaultDevice>('/api/appletv/default');
	},

	async addDeviceManually(
		address: string,
		name?: string
	): Promise<ApiResponse<{ device: PairedDevice; message: string }>> {
		return request<{ device: PairedDevice; message: string }>('/api/appletv/add', {
			method: 'POST',
			body: JSON.stringify({ address, name }),
		});
	},

	async deleteDevice(deviceId: string): Promise<ApiResponse<{ message: string }>> {
		return request<{ message: string }>(`/api/appletv/devices/${encodeURIComponent(deviceId)}`, {
			method: 'DELETE',
		});
	},

	async updateDevice(
		deviceId: string,
		data: { name?: string; address?: string }
	): Promise<ApiResponse<{ device: PairedDevice; message: string }>> {
		return request<{ device: PairedDevice; message: string }>(
			`/api/appletv/devices/${encodeURIComponent(deviceId)}`,
			{
				method: 'PATCH',
				body: JSON.stringify(data),
			}
		);
	},

	async getActivityLog(limit: number = 50): Promise<ApiResponse<{ entries: ActivityEntry[] }>> {
		return request<{ entries: ActivityEntry[] }>(`/api/appletv/activity?limit=${limit}`);
	},
};
