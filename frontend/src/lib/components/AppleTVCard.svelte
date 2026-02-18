<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import SettingsModal from './SettingsModal.svelte';
	import ToastContainer from './ToastContainer.svelte';
	import { api } from '../api';

	let url: string = '';
	let settingsOpen = false;
	let loading = false;
	let defaultDevice: { device_id: string; name: string } | null = null;

	async function loadDefaultDevice() {
		if (!browser) return;
		try {
			const response = await api.getDefaultDevice();
			if (response.ok && response.data) {
				defaultDevice = response.data.device_id
					? {
							device_id: response.data.device_id,
							name: response.data.name || 'Apple TV',
						}
					: null;
			}
		} catch (error) {
			console.error('Failed to load default device:', error);
		}
	}

	async function sendToAppleTV() {
		if (!url.trim()) {
			showToast('Введите URL', 'error');
			return;
		}

		if (!defaultDevice) {
			showToast('Выберите устройство Apple TV по умолчанию в настройках', 'error');
			settingsOpen = true;
			return;
		}

		loading = true;
		try {
			const response = await api.playUrl(url, defaultDevice.device_id);
			if (response.ok) {
				showToast('URL отправлен на Apple TV', 'success');
			} else {
				showToast(response.error?.message || 'Ошибка отправки URL', 'error');
			}
		} catch (error) {
			console.error('Play URL failed:', error);
			showToast('Ошибка отправки URL', 'error');
		} finally {
			loading = false;
		}
	}

	async function launch() {
		// For MVP, "Launch" also calls play URL
		// In future, this could launch a specific app
		await sendToAppleTV();
	}

	function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
		if (!browser) return;
		const event = new CustomEvent('toast:show', {
			detail: { message, type },
		});
		window.dispatchEvent(event);
	}

	function handleSettingsClose() {
		settingsOpen = false;
		loadDefaultDevice();
	}

	onMount(() => {
		loadDefaultDevice();
	});
</script>

<div class="appletv-card max-w-md mx-auto mt-8 p-6 bg-white rounded-lg shadow-lg">
	<div class="card-header mb-4">
		<h1 class="text-2xl font-bold text-center">Apple TV</h1>
	</div>

	<div class="card-body space-y-4">
		<div>
			<label for="url-input" class="block text-sm font-medium mb-2">
				URL / диплинк
			</label>
			<input
				id="url-input"
				type="text"
				bind:value={url}
				class="w-full border rounded px-3 py-2"
				placeholder="https://example.com/video.mp4"
				disabled={loading}
				on:keydown={(e) => {
					if (e.key === 'Enter') {
						sendToAppleTV();
					}
				}}
			/>
			<p class="text-xs text-gray-500 mt-1">
				Apple TV 3-го поколения: поддерживаются прямые ссылки (.mp4, .m3u8) и ссылки YouTube (воспроизведение через извлечение потока). Netflix и приложения — только на Apple TV 4-го поколения (tvOS).
			</p>
		</div>

		<div class="flex gap-2">
			<button
				class="flex-1 bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
				on:click={sendToAppleTV}
				disabled={loading || !url.trim()}
			>
				{loading ? 'Отправка...' : 'Отправить на Apple TV'}
			</button>
			<button
				class="flex-1 bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
				on:click={launch}
				disabled={loading || !url.trim()}
			>
				Запустить
			</button>
		</div>

		{#if defaultDevice}
			<p class="text-sm text-gray-600 text-center">
				Устройство по умолчанию: {defaultDevice.name}
			</p>
		{/if}
	</div>

	<div class="card-footer mt-4 flex justify-center">
		<button
			class="text-gray-600 hover:text-gray-800"
			on:click={() => (settingsOpen = true)}
			aria-label="Настройки"
		>
			<svg
				class="w-6 h-6"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
				xmlns="http://www.w3.org/2000/svg"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
				/>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
				/>
			</svg>
		</button>
	</div>
</div>

<SettingsModal isOpen={settingsOpen} onClose={handleSettingsClose} />
<ToastContainer />

<style>
	.appletv-card {
		font-family: system-ui, -apple-system, sans-serif;
	}
</style>
