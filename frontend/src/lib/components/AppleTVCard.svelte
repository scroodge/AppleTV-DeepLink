<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import SettingsModal from './SettingsModal.svelte';
	import ToastContainer from './ToastContainer.svelte';
	import { api } from '../api';
	import type { ActivityEntry } from '../types';

	let url: string = '';
	let quality: string = 'auto';
	let settingsOpen = false;
	let loading = false;
	let defaultDevice: { device_id: string; name: string } | null = null;
	let activityLog: ActivityEntry[] = [];
	let logPollInterval: ReturnType<typeof setInterval> | null = null;

	async function loadActivityLog() {
		if (!browser) return;
		try {
			const response = await api.getActivityLog(50);
			if (response.ok && response.data?.entries) {
				activityLog = response.data.entries;
			}
		} catch (e) {
			// ignore
		}
	}

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
		logPollInterval = window.setInterval(loadActivityLog, 1500);
		try {
			const response = await api.playUrl(url, defaultDevice.device_id, quality);
			await loadActivityLog();
			if (response.ok) {
				showToast('URL отправлен на Apple TV', 'success');
			} else {
				showToast(response.error?.message || 'Ошибка отправки URL', 'error');
			}
		} catch (error) {
			console.error('Play URL failed:', error);
			showToast('Ошибка отправки URL', 'error');
			await loadActivityLog();
		} finally {
			loading = false;
			if (logPollInterval) {
				clearInterval(logPollInterval);
				logPollInterval = null;
			}
		}
	}

	async function stopPlayback() {
		if (!defaultDevice) {
			showToast('Выберите устройство по умолчанию в настройках', 'error');
			return;
		}
		loading = true;
		try {
			const response = await api.stopPlayback();
			await loadActivityLog();
			if (response.ok) {
				showToast('Трансляция остановлена', 'success');
			} else {
				showToast(response.error?.message || 'Ошибка остановки', 'error');
			}
		} catch (error) {
			console.error('Stop failed:', error);
			showToast('Ошибка остановки', 'error');
			await loadActivityLog();
		} finally {
			loading = false;
		}
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

	function formatTime(ts: string) {
		try {
			const d = new Date(ts);
			return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
		} catch {
			return ts;
		}
	}

	onMount(() => {
		loadDefaultDevice();
		loadActivityLog();
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
			<div class="flex items-center gap-3 mt-2">
				<label for="quality-select" class="text-sm text-gray-600">Качество:</label>
				<select
					id="quality-select"
					bind:value={quality}
					class="border rounded px-2 py-1 text-sm"
					disabled={loading}
				>
					<option value="auto">Авто (лучшее)</option>
					<option value="1080p">1080p</option>
					<option value="720p">720p</option>
					<option value="480p">480p</option>
					<option value="360p">360p</option>
				</select>
				<span class="text-xs text-gray-500">для YouTube и подобных</span>
			</div>
			<p class="text-xs text-amber-600 mt-1">
				При 720p/1080p сервер может склеивать видео+звук (ffmpeg). Задайте STREAM_BASE_URL (IP ПК в сети), чтобы Apple TV мог загрузить поток — тогда будет 720p/1080p со звуком.
			</p>
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
				class="px-4 py-2 border border-gray-400 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
				on:click={stopPlayback}
				disabled={loading}
			>
				Остановить трансляцию
			</button>
		</div>
		<p class="text-xs text-gray-500">
			Чтобы сменить качество: нажмите «Остановить трансляцию», выберите качество в списке и снова «Отправить на Apple TV».
		</p>

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

<div class="activity-log mt-6 max-w-2xl mx-auto">
	<h2 class="text-sm font-semibold text-gray-600 mb-2">Журнал операций со ссылками</h2>
	<div class="bg-gray-900 text-gray-100 rounded-lg p-3 font-mono text-xs overflow-x-auto max-h-48 overflow-y-auto">
		{#if activityLog.length === 0}
			<p class="text-gray-500">Пока нет записей. Отправьте ссылку на Apple TV.</p>
		{:else}
			{#each activityLog as entry, i (entry.ts + String(i) + (entry.message || ''))}
				<div class="flex gap-2 py-1 border-b border-gray-700 last:border-0 items-start">
					<span class="text-gray-500 shrink-0">{formatTime(entry.ts)}</span>
					<span
						class="shrink-0 font-semibold {entry.status === 'success'
						? 'text-green-400'
						: entry.status === 'error'
							? 'text-red-400'
							: 'text-yellow-400'}"
					>
						{entry.status === 'start' ? '…' : entry.status === 'success' ? 'OK' : 'ERR'}
					</span>
					<span class="min-w-0 break-all flex-1">
						{#if entry.url}
							<span class="text-gray-400">{entry.url}</span>
							{#if entry.device}
								<span class="text-gray-500"> → {entry.device}</span>
							{/if}
							<br />
						{/if}
						{entry.message}
						{#if entry.status === 'success'}
							{@const isMerge = entry.merge_used ?? (!!(entry.message && entry.message.includes('склейка на сервере')))}
							<div class="mt-1 text-gray-500">
								Вариант:
								{#if isMerge}
									<span class="px-1.5 py-0.5 rounded text-green-300 bg-green-900/50 font-medium" title="Видео и звук склеены на сервере (ffmpeg)">склейка на сервере</span>
								{:else}
									<span class="px-1.5 py-0.5 rounded text-gray-400 bg-gray-700/50 font-medium" title="Один поток с yt-dlp">прямой поток</span>
								{/if}
							</div>
						{/if}
					</span>
				</div>
			{/each}
		{/if}
	</div>
</div>

<SettingsModal isOpen={settingsOpen} onClose={handleSettingsClose} />
<ToastContainer />

<style>
	.appletv-card {
		font-family: system-ui, -apple-system, sans-serif;
	}
	.activity-log {
		font-family: system-ui, -apple-system, sans-serif;
	}
</style>
