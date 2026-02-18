<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import DeviceList from './DeviceList.svelte';
	import PairingFlow from './PairingFlow.svelte';
	import { api } from '../api';
	import type { DeviceInfo, PairedDevice, DefaultDevice } from '../types';

	export let isOpen: boolean = false;
	export let onClose: () => void = () => {};

	let devices: DeviceInfo[] = [];
	let pairedDevices: PairedDevice[] = [];
	let defaultDevice: DefaultDevice | null = null;
	let scanning = false;
	let pairingDevice: DeviceInfo | null = null;
	let pairingProtocol: string = '';
	let loading = false;
	let showAddManual = false;
	let manualAddress = '';
	let manualName = '';

	async function loadData() {
		loading = true;
		try {
			const [devicesRes, pairedRes, defaultRes] = await Promise.all([
				api.getPairedDevices(),
				api.getPairedDevices(),
				api.getDefaultDevice(),
			]);

			if (pairedRes.ok && pairedRes.data) {
				pairedDevices = pairedRes.data.devices;
			}
			if (defaultRes.ok && defaultRes.data) {
				defaultDevice = defaultRes.data;
			}
		} catch (error) {
			console.error('Failed to load data:', error);
		} finally {
			loading = false;
		}
	}

	async function scanDevices() {
		scanning = true;
		try {
			const response = await api.scanDevices();
			if (response.ok && response.data) {
				devices = response.data.devices;
				// Merge with paired devices
				await loadData();
			} else {
				showToast(response.error?.message || 'Ошибка сканирования', 'error');
			}
		} catch (error) {
			console.error('Scan failed:', error);
			showToast('Ошибка сканирования устройств', 'error');
		} finally {
			scanning = false;
		}
	}

	async function handlePair(device: DeviceInfo, protocol: string) {
		pairingDevice = device;
		pairingProtocol = protocol;
		loading = true;

		try {
			const response = await api.startPairing(device.device_id, protocol);
			if (response.ok && response.data) {
				if (response.data.status === 'PIN_REQUIRED') {
					showToast('Введите PIN с экрана Apple TV', 'info');
					// PairingFlow already visible (pairingDevice is set)
				} else if (response.data.status === 'CREDENTIALS_REQUIRED') {
					showToast('Требуются учётные данные — попробуйте другой протокол', 'info');
					pairingDevice = null;
				} else if (response.data.status === 'COMPLETED') {
					showToast('Сопряжение завершено успешно', 'success');
					pairingDevice = null;
					await loadData();
				} else {
					showToast(response.data.message || 'Неизвестный статус сопряжения', 'info');
				}
			} else {
				showToast(response.error?.message || 'Ошибка сопряжения', 'error');
				pairingDevice = null;
			}
		} catch (error) {
			console.error('Pairing failed:', error);
			showToast('Ошибка сопряжения', 'error');
			pairingDevice = null;
		} finally {
			loading = false;
		}
	}

	async function handlePinSubmit(pin: string) {
		if (!pairingDevice) return;

		loading = true;
		try {
			const response = await api.submitPin(pairingDevice.device_id, pin);
			if (response.ok && response.data) {
				if (response.data.status === 'COMPLETED') {
					showToast('Сопряжение завершено успешно', 'success');
					pairingDevice = null;
					await loadData();
				}
			} else {
				showToast(response.error?.message || 'Неверный PIN', 'error');
			}
		} catch (error) {
			console.error('PIN submission failed:', error);
			showToast('Ошибка при отправке PIN', 'error');
		} finally {
			loading = false;
		}
	}

	async function handleSetDefault(deviceId: string) {
		loading = true;
		try {
			const response = await api.setDefaultDevice(deviceId);
			if (response.ok) {
				showToast('Устройство по умолчанию установлено', 'success');
				await loadData();
			} else {
				showToast(response.error?.message || 'Ошибка установки устройства', 'error');
			}
		} catch (error) {
			console.error('Set default failed:', error);
			showToast('Ошибка установки устройства', 'error');
		} finally {
			loading = false;
		}
	}

	async function handleAddManual() {
		if (!manualAddress.trim()) {
			showToast('Введите IP адрес', 'error');
			return;
		}

		loading = true;
		try {
			const response = await api.addDeviceManually(
				manualAddress.trim(),
				manualName.trim() || undefined
			);
			if (response.ok && response.data) {
				showToast(response.data.message || 'Устройство добавлено', 'success');
				manualAddress = '';
				manualName = '';
				showAddManual = false;
				await loadData();
			} else {
				showToast(response.error?.message || 'Ошибка добавления устройства', 'error');
			}
		} catch (error) {
			console.error('Add device failed:', error);
			showToast('Ошибка добавления устройства', 'error');
		} finally {
			loading = false;
		}
	}

	async function handleDelete(deviceId: string) {
		if (!confirm('Удалить это устройство из списка?')) return;
		loading = true;
		try {
			const response = await api.deleteDevice(deviceId);
			if (response.ok) {
				showToast('Устройство удалено', 'success');
				await loadData();
			} else {
				showToast(response.error?.message || 'Ошибка удаления', 'error');
			}
		} catch (error) {
			console.error('Delete device failed:', error);
			showToast('Ошибка удаления устройства', 'error');
		} finally {
			loading = false;
		}
	}

	async function handleUpdate(deviceId: string, data: { name?: string; address?: string }) {
		loading = true;
		try {
			const response = await api.updateDevice(deviceId, data);
			if (response.ok) {
				showToast('Устройство обновлено', 'success');
				await loadData();
			} else {
				showToast(response.error?.message || 'Ошибка сохранения', 'error');
			}
		} catch (error) {
			console.error('Update device failed:', error);
			showToast('Ошибка обновления устройства', 'error');
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

	function handleCancelPairing() {
		pairingDevice = null;
		pairingProtocol = '';
	}

	onMount(() => {
		if (isOpen) {
			loadData();
		}
	});

	$: if (isOpen) {
		loadData();
	}
</script>

{#if isOpen}
	<div
		class="modal-overlay fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
		on:click={onClose}
		role="dialog"
		aria-modal="true"
	>
		<div
			class="modal-content bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto"
			on:click|stopPropagation
		>
			<div class="modal-header p-4 border-b flex justify-between items-center">
				<h2 class="text-xl font-semibold">Настройки Apple TV</h2>
				<button
					class="text-gray-500 hover:text-gray-700 text-2xl"
					on:click={onClose}
					aria-label="Закрыть"
				>
					×
				</button>
			</div>
			<div class="modal-body p-4 space-y-4">
				<div class="flex gap-2">
					<button
						class="flex-1 bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
						on:click={scanDevices}
						disabled={scanning || loading}
					>
						{scanning ? 'Сканирование...' : 'Сканировать устройства'}
					</button>
					<button
						class="flex-1 bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
						on:click={() => (showAddManual = !showAddManual)}
						disabled={loading}
					>
						{showAddManual ? 'Отмена' : 'Добавить вручную'}
					</button>
				</div>

				{#if showAddManual}
					<div class="border rounded p-4 bg-gray-50">
						<h3 class="font-semibold mb-3">Добавить устройство по IP</h3>
						<div class="space-y-3">
							<div>
								<label class="block text-sm font-medium mb-1">IP адрес *</label>
								<input
									type="text"
									bind:value={manualAddress}
									class="w-full border rounded px-3 py-2"
									placeholder="192.168.1.100"
									disabled={loading}
								/>
							</div>
							<div>
								<label class="block text-sm font-medium mb-1">Название (необязательно)</label>
								<input
									type="text"
									bind:value={manualName}
									class="w-full border rounded px-3 py-2"
									placeholder="Apple TV"
									disabled={loading}
								/>
							</div>
							<button
								class="w-full bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
								on:click={handleAddManual}
								disabled={loading || !manualAddress.trim()}
							>
								{loading ? 'Добавление...' : 'Добавить устройство'}
							</button>
						</div>
					</div>
				{/if}

				{#if pairingDevice}
					<PairingFlow
						device={pairingDevice}
						protocol={pairingProtocol}
						onPinSubmit={handlePinSubmit}
						onCancel={handleCancelPairing}
					/>
				{/if}

				<div>
					<h3 class="font-semibold mb-2">Обнаруженные устройства</h3>
					<DeviceList
						{devices}
						{pairedDevices}
						defaultDeviceId={defaultDevice?.device_id || null}
						onPair={handlePair}
						onSetDefault={handleSetDefault}
					/>
				</div>

				{#if pairedDevices.length > 0}
					<div>
						<h3 class="font-semibold mb-2">Добавленные устройства</h3>
						<DeviceList
							devices={pairedDevices.map((d) => ({
								device_id: d.device_id,
								name: d.name,
								address: d.address,
								protocols: d.protocols,
							}))}
							{pairedDevices}
							defaultDeviceId={defaultDevice?.device_id || null}
							onPair={handlePair}
							onSetDefault={handleSetDefault}
							onDelete={handleDelete}
							onUpdate={handleUpdate}
						/>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		backdrop-filter: blur(2px);
	}
</style>
